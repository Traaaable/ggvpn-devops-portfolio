# GG VPN — Docker и Helm: практическая работа

Самостоятельный воспроизводимый стенд для демонстрации контейнеризации,
развёртывания и сопровождения веб-сервиса в Kubernetes. В основе — учебный chart
GG VPN, доработанный до проверяемого сценария установки, обновления и отката.
Дополнительно приложены обезличенные фрагменты существующего VPN-проекта.

Это практическая работа на Nginx. Она не является утверждением о переносе
боевого GG VPN в Kubernetes или об эксплуатации GKE.

## Что посмотреть

| Файл | Назначение |
|---|---|
| [Helm chart](charts/ggvpn-web) | Deployment, Service, ConfigMap, probes, Ingress, HPA, PDB, NetworkPolicy |
| [Dockerfile](docker/web/Dockerfile), [Compose](compose.yaml) | Запускаемый web-стенд без root, с read-only rootfs и лимитами |
| [Контрактные проверки](tests/test_chart.py) | Связи ресурсов, произвольные release names, порт сервиса, обновление ConfigMap |
| [Проверка в Kubernetes](scripts/integration.sh) | Два независимых релиза, upgrade, контролируемый сбой и rollback |
| [DNSTT](examples/dnstt) | Многоэтапная Go-сборка с закреплённой версией |
| [GG VPN app](examples/ggvpn-app) | Фрагменты реальной архитектуры bot/web/worker; требуют исходников приложения |
| [Ansible](examples/ansible) | Параметризованный Compose агента мониторинга |
| [Отчёт проверки](docs/VALIDATION.md) | Выполненные проверки и границы доказанного |
| [Кейс проекта](docs/CASE.md) | Контекст практического опыта |

## Docker: быстрый запуск

Нужны Docker Engine и Docker Compose v2. Команды выполняются из корня репозитория.

```bash
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:18080/
curl -fsS http://127.0.0.1:18080/healthz
docker compose down
```

Порт доступен только на loopback. При занятом порте:
`PORTFOLIO_HTTP_PORT=18082 docker compose up -d --build --wait`.
Контейнеру не нужны `.env`, токены, SSH, Docker socket или пользовательские данные.

## Kubernetes: быстрый запуск

Нужны Helm 3.14+ либо Helm 4, kubectl и тестовый Kubernetes 1.27+.
Chart использует закреплённый официальный Nginx-образ, поэтому собирать
и публиковать свой образ для первого запуска не требуется.

```bash
# Просмотрите доступные контексты и выберите именно тестовый кластер.
kubectl config get-contexts
export KUBE_CONTEXT=your-test-context

helm --kube-context "$KUBE_CONTEXT" install demo charts/ggvpn-web \
  -n portfolio-demo --create-namespace -f values-dev.yaml --wait --timeout 180s
helm --kube-context "$KUBE_CONTEXT" test demo -n portfolio-demo --logs
kubectl --context "$KUBE_CONTEXT" -n portfolio-demo \
  port-forward svc/demo-ggvpn-web 18080:80
```

В другом терминале: `curl -fsS http://127.0.0.1:18080/`.
Остановка port-forward — `Ctrl+C`. Удаление:

```bash
helm --kube-context "$KUBE_CONTEXT" uninstall demo -n portfolio-demo
kubectl --context "$KUBE_CONTEXT" delete namespace portfolio-demo
```

Удаляйте namespace только если создали его специально для этой работы.

## Проверки

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
bash scripts/check.sh
bash scripts/docker-smoke.sh
bash scripts/dnstt-smoke.sh
KUBE_CONTEXT=your-test-context bash scripts/integration.sh
```

Интеграционный скрипт создаёт уникальный namespace с ограничениями Pod Security,
проверяет два имени релиза, обновление содержимого и порта, намеренно неудачное
обновление и восстановление прежней версии. В конце удаляет свой namespace.
Не запускайте нагрузочные эксперименты на рабочем кластере.

Инструкции по Ingress/TLS, HPA, диагностике и обновлению:
[RUNBOOK.md](docs/RUNBOOK.md). Сценарий объяснения работы на интервью:
[INTERVIEW.md](docs/INTERVIEW.md).

## CI

GitHub Actions содержит проверки chart, Docker smoke test и отдельный
Kubernetes integration job. CI не разворачивает приложение на внешних серверах
и не использует production-секреты. Текущий статус запусков смотрите во вкладке
Actions; наличие workflow само по себе не доказывает успешный запуск.

## Происхождение

Chart переработан из локальной лабораторной работы `ggvpn-web` версии 0.2.0.
Часть helpers и шаблонов происходят из стандартного каркаса Helm.
Docker/Ansible-фрагменты взяты из GG VPN и адаптированы для публичного примера.
Доработка и проверки выполнены с помощью Codex; автору портфолио следует уметь
самостоятельно повторить сценарии и объяснить решения.
