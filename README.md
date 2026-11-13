# RunBack · prototype 0.1.0

Small, explicit backups for notebook experiments. **No cloud account, no network calls, no paid API.** Python 3.10+; runtime uses only the standard library.

## Зачем
Colab может сбросить `/content`. RunBack сохраняет **выбранные вами файлы** в ZIP, проверяет SHA256 и восстанавливает их в новую папку. Снимок нужно положить на уже подключённый Google Drive или скачать на свой компьютер. ZIP в `/content` не переживёт сброс.

Это рабочий локальный прототип, не проверенный в живой сессии Colab. Не обещает сохранность данных или автоматическое продолжение обучения. Не публиковался на PyPI. Название пакета на PyPI не проверено: не устанавливайте одноимённый пакет из интернета.

## Первый запуск без установки
Распакуйте проект и откройте терминал в папке с этим README:

```bash
python -m runback --help
python -m unittest discover -s tests -v
python examples/demo.py
```

Demo создаёт собственную временную папку, сохраняет два вымышленных файла, проверяет архив, восстанавливает в другую папку и сравнивает байты. Не трогает ваши эксперименты.

## Реальный эксперимент
```bash
python -m runback doctor --storage /path/to/persistent/backups
python -m runback snapshot --root /path/to/experiment \
  --include pipeline.py --include config.json --include metrics.json \
  --output /path/to/persistent/backups/experiment-001.zip
python -m runback verify /path/to/persistent/backups/experiment-001.zip
python -m runback restore /path/to/persistent/backups/experiment-001.zip \
  --to /path/to/new-restored-experiment
```
`--include` повторяется для каждого **файла**, пути относительно `--root`. Папки и glob не поддерживаются, чтобы вы не сохранили лишнее. Родитель новой папки восстановления должен существовать. Используйте физический путь без симлинков: на macOS `/tmp` и `/var` обычно являются ссылками; реальный путь можно проверить через `Path(path).resolve()` в Python. Имя архива и папка восстановления должны быть новыми. Код из архива никогда не запускается. Команды возвращают JSON и код 0 при успехе, 1 при ошибке.

`doctor` проверяет запись и свободное место, **не доказывает постоянство хранилища** и не подключает Drive. GPU для резервных копий не требуется.

## Colab: быстрое начало
1. Загрузите папку проекта в Google Drive. В Colab самостоятельно подключите свой Drive:
```python
from google.colab import drive
drive.mount('/content/drive')
```
2. Укажите путь к папке, где лежат README и подпапка `runback`. Например:
```python
%cd /content/drive/MyDrive/runback
!python -m runback --help
```
3. Создайте папку для снимков и проверьте доступ:
```python
from pathlib import Path
Path('/content/drive/MyDrive/runback-backups').mkdir(exist_ok=True)
!python -m runback doctor --storage /content/drive/MyDrive/runback-backups
```
4. Пока эксперимент ещё существует, выберите свои файлы (замените пути):
```python
!python -m runback snapshot --root /content/experiment --include pipeline.py --include metrics.json --output /content/drive/MyDrive/runback-backups/experiment-001.zip
!python -m runback verify /content/drive/MyDrive/runback-backups/experiment-001.zip
```
Проверьте наличие ZIP через интерфейс Drive; сохраните вторую копию отдельно. После сброса вновь подключите Drive, выполните `%cd`, затем:
```python
!python -m runback restore /content/drive/MyDrive/runback-backups/experiment-001.zip --to /content/experiment-restored
```
RunBack не восстанавливает GPU-сессию, установленные пакеты, RAM, оптимизатор или незаписанные результаты. Для повторного запуска сохраняйте также собственный файл зависимостей и seed/config. Не включайте переменные окружения целиком.

## Защита и ограничения
- Максимум 1 000 файлов и 50 MiB данных на снимок. Большие веса моделей не цель первой версии.
- Скрытые пути, симлинки, подозрительные имена секретов, некоторые токены/пароли в содержимом отклоняются. Это **эвристика**, не гарантия: вручную проверьте каждый файл, включая выводы ноутбуков, логи, персональные данные и неизвестные форматы ключей. Проверка может дать ложное срабатывание. Обхода проверки нет.
- Архив **не зашифрован**. SHA256 выявляет порчу, но не доказывает подлинность: злоумышленник может заменить и содержимое, и manifest. Не открывайте чужой код без проверки.
- Архив полностью проверяется до восстановления; абсолютные пути, traversal, лишние записи, дубликаты и симлинки отвергаются. Перезапись существующих файлов запрещена.
- Запускайте только в своей доверенной папке без параллельного изменения файлов. Не предназначено для враждебных локальных пользователей, atomic point-in-time snapshot, backup серверов или аварийного восстановления production. Прерванная запись может оставить неполный ZIP: `verify` перед использованием обязателен.
- Запись ZIP на Drive не подтверждает завершение синхронизации сервиса. Проверяйте копию отдельно.
- Не собиратель данных: телеметрии и сетевых запросов нет. Manifest содержит выбранные относительные имена, размеры, хэши, UTC и версию Python, не hostname/username/env.

## Existing alternatives
This does not replace Hugging Face Trainer checkpoints/resume, MLflow experiment tracking, DVC data versioning, or tools such as `ehzawad/colab-persist`. RunBack explores a smaller, explicit-files workflow for beginners. Demand and usefulness have not yet been validated.

## Проверка спроса
Дайте демо 5 студентам; посмотрите, смогут ли хотя бы 3 самостоятельно сохранить и восстановить реальные небольшие результаты и захотят ли повторить. Не считайте количество скачиваний доказательством пользы. Новый репозиторий не гарантирует участие в программах поддержки open source.

## Development
```bash
python -m unittest discover -s tests -v
python -m compileall -q runback examples tests
```
Tested locally on Linux and macOS: 26 unit tests and the snapshot/verify/restore demo. Live Colab reconnect, Windows, and unusual filesystems remain untested. No paid dependencies.

## License
MIT. Copyright (c) 2026 Ертай Арлан Бақытұлы. See [LICENSE](LICENSE).
