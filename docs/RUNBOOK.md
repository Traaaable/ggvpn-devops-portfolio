# Эксплуатация лабораторного стенда

## Архитектура

`клиент → Ingress (опционально) → Service → Nginx Pod → ConfigMap`

Service слушает на порту из values, контейнер — на фиксированном 8080.
ConfigMap хранит страницу и nginx.conf, смонтированные в разные каталоги.
Конфигурация Nginx не отдаётся как статический файл.
`checksum/content` меняет шаблон Pod при обновлении конфигурации.

Nginx работает с UID/GID 101, read-only root filesystem, без capabilities и
ServiceAccount token. Временные файлы записываются в отдельный emptyDir `/tmp`.
Логи направляются в stdout/stderr.

`startupProbe` допускает медленный старт; `livenessProbe` проверяет HTTP-процесс;
`readinessProbe` дополнительно проверяет наличие страницы. Это простой статический
сервис, поэтому здесь нет проверки БД или внешних API.

## Обновление и откат

Команды ниже предполагают release `demo` в namespace `portfolio-demo`.
Явный `--kube-context "$KUBE_CONTEXT"` обязателен при работе с несколькими кластерами.

```bash
helm --kube-context "$KUBE_CONTEXT" upgrade demo charts/ggvpn-web \
  -n portfolio-demo -f values-dev.yaml \
  --set-string pageContent='<h1>Release v2</h1>' --wait --timeout 180s
helm --kube-context "$KUBE_CONTEXT" test demo -n portfolio-demo --logs
helm --kube-context "$KUBE_CONTEXT" history demo -n portfolio-demo
helm --kube-context "$KUBE_CONTEXT" rollback demo 1 \
  -n portfolio-demo --wait --timeout 180s
helm --kube-context "$KUBE_CONTEXT" test demo -n portfolio-demo --logs
```

Номер для rollback выбирается из history, а не всегда равен 1.
`--wait` сам по себе не откатывает неудачный upgrade. В интеграционном сценарии
это сделано явно. Для автоматического отката Helm 3 использует `--atomic`,
Helm 4 — `--rollback-on-failure`; проверяйте `helm upgrade --help` своей версии.
Helm rollback не откатывает внешнюю БД; в этом стенде БД нет.

Тестовый Pod сохраняется после завершения, чтобы `helm test --logs` работал
и на Helm 3, и на Helm 4. Следующий запуск теста удаляет предыдущий Pod
через `before-hook-creation`. Интеграционный сценарий удаляет весь свой namespace.
При работе в общем namespace после проверки можно удалить только тестовый Pod:
`kubectl --context "$KUBE_CONTEXT" -n portfolio-demo delete pod demo-ggvpn-web-test`.

## Ingress и TLS

```bash
kubectl --context "$KUBE_CONTEXT" get ingressclass
helm --kube-context "$KUBE_CONTEXT" upgrade demo charts/ggvpn-web \
  -n portfolio-demo -f values-dev.yaml -f values-ingress.yaml --wait
```

Файл рассчитан на установленный контроллер с классом `nginx`.
Если в лаборатории установлен Traefik, используйте `--set ingress.className=traefik`.
Chart не устанавливает контроллер и не управляет его жизненным циклом.
Для HTTP-проверки направьте hostname `portfolio.example.test` на адрес контроллера
или передайте заголовок Host при запросе к этому адресу.

Для TLS создайте Secret в namespace релиза средствами вашей тестовой среды:

```yaml
ingress:
  tls:
    - secretName: portfolio-tls
      hosts:
        - portfolio.example.test
```

Сертификат, ключ и автоматический выпуск сертификата не входят в подборку.
Не добавляйте приватные ключи в Git.

## HPA и ресурсы

```bash
kubectl --context "$KUBE_CONTEXT" top pods -n portfolio-demo
helm --kube-context "$KUBE_CONTEXT" upgrade demo charts/ggvpn-web \
  -n portfolio-demo -f values-hpa.yaml --wait
kubectl --context "$KUBE_CONTEXT" get hpa -n portfolio-demo
```

Нужен доступный resource metrics API, обычно через metrics-server.
HPA использует CPU utilization относительно requests (здесь 25m), а не относительно
лимита CPU. При включённом HPA поле replicas в Deployment не задаётся.
Минимум — 2, максимум — 4 Pod. Проверка HPA под искусственной нагрузкой
не является измерением вместимости сервиса или числа клиентов.

## PDB и сеть

По умолчанию PDB сохраняет минимум одну доступную реплику при добровольных
эвикциях. `values-dev.yaml` отключает PDB для одного Pod.
PDB не обеспечивает отказоустойчивость одного узла и не управляет RollingUpdate;
для обновлений Deployment задано `maxUnavailable: 0`.

Опционально:

```bash
helm --kube-context "$KUBE_CONTEXT" upgrade demo charts/ggvpn-web \
  -n portfolio-demo -f values-dev.yaml \
  --set networkPolicy.enabled=true \
  --set networkPolicy.ingressNamespace=ingress-nginx --wait
```

NetworkPolicy разрешает вход на 8080 из того же namespace и namespace
контроллера Ingress. Исходящий трафик приложения запрещён. Нужен CNI,
реально применяющий NetworkPolicy; простого создания ресурса недостаточно
для доказательства сетевой изоляции.

## Диагностика

```bash
kubectl --context "$KUBE_CONTEXT" -n portfolio-demo get pods,svc,ingress,hpa,pdb
kubectl --context "$KUBE_CONTEXT" -n portfolio-demo describe pod POD_NAME
kubectl --context "$KUBE_CONTEXT" -n portfolio-demo logs deploy/demo-ggvpn-web
kubectl --context "$KUBE_CONTEXT" -n portfolio-demo get events --sort-by=.lastTimestamp
helm --kube-context "$KUBE_CONTEXT" get values demo -n portfolio-demo
```

- `ImagePullBackOff`: проверьте образ, digest и доступ к registry.
- `CrashLoopBackOff`: смотрите предыдущие логи, nginx.conf и права на `/tmp`.
- `Pending`: проверьте requests, свободные ресурсы и ограничения планировщика.
- `HPA <unknown>`: проверьте metrics API и наличие CPU requests.
- `Ingress 404`: проверьте ingressClassName, Host и адрес контроллера.

## Дополнительные интеграционные проверки

В отдельном лабораторном кластере с metrics-server, Ingress и CNI с поддержкой
NetworkPolicy можно воспроизвести проверку HTTP-маршрута, сетевой изоляции и
масштабирования с 2 до 3 Pod:

```bash
KUBE_CONTEXT=your-test-context \
INGRESS_CLASS=traefik INGRESS_NAMESPACE=kube-system INGRESS_SERVICE=traefik \
python3 scripts/check_optional.py
```

Для контроллера Nginx укажите его класс, namespace и имя Service.
Скрипт создаёт два временных namespace, использует локальный порт 18083 и
удаляет созданные ресурсы. Нагрузка ограничена одним процессом на 65 секунд
в контейнере с лимитом 200m CPU. При занятом порте задайте `PORTFOLIO_INGRESS_PORT`.
Это проверка работы HPA, а не нагрузочный тест бизнеса.

## Источники

- [Helm chart tests](https://v3.helm.sh/docs/topics/chart_tests/)
- [Kubernetes HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)
- [Официальные Nginx Dockerfiles](https://github.com/nginx/docker-nginx)
