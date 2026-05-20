# Feature Flags Module

Feature flags with percentage rollouts, targeting rules, and A/B testing.

## Setup

```python
from vorte import FeaturesModule

app.register(FeaturesModule())
```

## Configuration

```env
VORTE_FEATURES_DRIVER=database
```

## Features

### Boolean Flags

Simple on/off switches:

```python
from vorte.modules.features import FeatureFlagManager

manager = FeatureFlagManager()
manager.set("dark_mode", enabled=True)
```

### Percentage Rollouts

Gradually roll out features using MD5 hash bucketing:

```python
# Roll out to 25% of users
manager.set("new_dashboard", percentage=25)
```

### User Targeting

Target specific users or groups:

```python
manager.set("beta_feature", targeting=["user_123", "user_456"])
```

### A/B Testing

Define experiment variants:

```python
manager.set("checkout_flow", variants={
    "control": {"percentage": 50},
    "variant_a": {"percentage": 50},
})
```

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/features` | GET | List all flags |
| `/features/{name}` | GET | Get flag status |
| `/features/{name}` | POST | Set flag |
| `/features/{name}` | DELETE | Delete flag |
