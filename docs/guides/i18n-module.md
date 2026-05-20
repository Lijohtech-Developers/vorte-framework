# Internationalization Module (i18n)

Multi-language support with translation files, formatting, and locale detection.

## Setup

```python
from vorte import I18nModule

app.register(I18nModule())
```

## Configuration

```env
VORTE_I18N_DEFAULT_LOCALE=en
VORTE_I18N_FALLBACK_LOCALE=en
VORTE_I18N_LOCALES_DIR=./locales
```

## Translation Files

Create JSON translation files in the locales directory:

```
locales/
├── en.json
├── sw.json    # Swahili
└── fr.json    # French
```

Example `locales/en.json`:

```json
{
  "welcome": "Welcome to {app}!",
  "goodbye": "Goodbye, {name}!",
  "errors.not_found": "The requested resource was not found"
}
```

Example `locales/sw.json`:

```json
{
  "welcome": "Karibu {app}!",
  "goodbye": "Kwaheri, {name}!",
  "errors.not_found": "Rasilimali iliyoombwa haipatikani"
}
```

## Features

### Variable Interpolation

```python
from vorte.modules.i18n import Translator

translator = Translator(locale="en")
text = translator.translate("welcome", app="Vorte")
# "Welcome to Vorte!"
```

### Locale Detection

Automatically detects locale from:
- `Accept-Language` header
- URL parameter (`?locale=sw`)
- User preference
- Default locale

### Formatting

- **Currency** -- Locale-aware currency formatting
- **Dates** -- Locale-aware date formatting
- **Numbers** -- Locale-aware number formatting

### Built-in Languages

Swahili is included out of the box for East African deployments.
