# Дизайн сайта через Photopea API

Скилл для Claude Code и Codex. Результат: финальные макеты, превью и редактируемые PSD. Исследование, варианты скетчей, подбор шрифтов, прототипы и визуальные проверки входят в процесс. Учебный отчёт не создаётся по умолчанию.

## Claude Code

Скопируйте `SKILL.md`, `scripts/`, `references/` и `assets/` из этого репозитория в папку `~/.claude/skills/photopea-coursework-design/`. Файл `agents/openai.yaml` используется Codex; для Claude Code он не нужен.

Пример установки в PowerShell после клонирования репозитория в `D:\Codex\design-skill`:

```powershell
$skillSource = 'D:\Codex\design-skill'
$skillTarget = Join-Path $env:USERPROFILE '.claude\skills\photopea-coursework-design'
New-Item -ItemType Directory -Force -Path $skillTarget | Out-Null
foreach ($item in @('SKILL.md', 'scripts', 'references', 'assets')) {
    Copy-Item -LiteralPath (Join-Path $skillSource $item) -Destination $skillTarget -Recurse -Force
}
```

Вызов в Claude Code:

```text
/photopea-coursework-design Создай дизайн сайта [описание, аудитория, нужные экраны и референсы]. Выдай макеты, превью и редактируемые PSD.
```

Для установки только в одном проекте используйте `<проект>/.claude/skills/photopea-coursework-design/`. Формат и расположение описаны в [документации Claude Code](https://code.claude.com/docs/en/skills).

## Codex

Скопируйте `SKILL.md`, `scripts/`, `references/`, `assets/` и `agents/` в `~/.codex/skills/photopea-coursework-design/`. Вызов: `$photopea-coursework-design` с описанием сайта. Идентификатор сохранён для совместимости с уже установленным скиллом.

## Как используется Photopea

Основной маршрут: HTML/CSS → DOM-сцена → SVG → Photopea Live Messaging API → PSD/PNG. Python и Playwright запускают браузер и передают данные iframe. `postMessage` отправляет файл как `ArrayBuffer`, скрипт — строкой; Photopea возвращает результат через `saveToOE` и подтверждение `done`. Подробнее: [рабочий конвейер](references/psd-pipeline.md), [официальный API](https://www.photopea.com/api/live).

Для полного runner нужны Python, Pillow, psd-tools, Playwright и Chrome. Сначала проверяйте существующую среду; зависимости и ресурсы устанавливайте по инструкциям проекта. Если самостоятельный Playwright ограничен, предусмотрен локальный мост с тем же API через разрешённый браузерный инструмент.
