# 🌌 Vorte Framework

**The AI-First, Battery-Included Python API Framework.**

Vorte is a high-performance Python framework designed for modern web development, with a specific focus on AI agents, real-time monitoring, and seamless developer experience. It bridges the gap between powerful backends and stunning, real-time administrative interfaces.

---

## ✨ Key Features

- 🚀 **Built-in Dashboard**: A premium Next.js admin panel automatically served at `/vorte/dashboard`.
- 🧠 **AI-First**: Native support for AI agents, pipelines, and cost tracking out of the box.
- 🛠️ **Module System**: Highly decoupled architecture—only use what you need.
- ⚡ **High Performance**: Built on top of FastAPI and Uvicorn for maximum throughput.
- 📱 **M-Pesa Integration**: First-class support for Safaricom M-Pesa (Daraja) operations.
- 📊 **Real-time Metrics**: Track traffic, latency, and system health in real-time.
- 🐳 **Cloud Ready**: Auto-generates Docker and Kubernetes manifests.

---

## 🚀 Quick Start

### 1. Install Vorte
```bash
pip install vorte
```

### 2. Scaffold Your Project
```bash
vorte new my-awesome-app
cd my-awesome-app
```

### 3. Launch
```bash
vorte serve --watch
```
Visit `http://localhost:8000/vorte/dashboard` to see your new console!

---

## 🏗️ Architecture

Vorte follows a modular "Core + Plugins" architecture. The core provides the engine, while modules handle specific functionality like AI, Database, and Auth.

```python
from vorte import Vorte

app = Vorte(auto_load=True)

@app.get("/api/v1/hello")
async def hello():
    return {"message": "Welcome to Vorte!"}
```

---

## 🎨 Dashboard Customization

The dashboard is built with **Next.js**, **Tailwind CSS**, and **Framer Motion**. You can find the source in the `src/` directory if you wish to build custom modules or skins.

---

## 📄 License

Vorte is released under the **MIT License**.

## 🤝 Contributing

We welcome contributions! Please check the issues or submit a pull request.

---

*Built with ❤️ for developers who value speed, aesthetics, and intelligence.*
