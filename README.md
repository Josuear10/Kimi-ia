# 🥝 Kiwi.ia

**Tu asistente de inteligencia artificial que recuerda tus conversaciones.**

Kiwi.ia es un chat con IA donde puedes preguntar lo que quieras: aprender un tema nuevo,
pedir ideas, resumir textos o redactar mensajes. Inicia sesión con tu cuenta y Kiwi guardará
tus conversaciones para que puedas retomarlas cuando quieras.

---

## ✨ ¿Qué puedes hacer con Kiwi?

- 💬 **Conversar con IA**: respuestas claras y bien formateadas, impulsadas por Claude.
- 🧠 **Seguir donde lo dejaste**: Kiwi recuerda lo que hablaron antes en cada conversación.
- 📚 **Ver tu historial**: todas tus conversaciones en un solo lugar, listas para abrir o borrar.
- 🔐 **Entrar fácil**: con tu correo, o con Google o Apple.
- 🔒 **Privacidad**: solo tú puedes ver tus conversaciones.
- 📱 **Desde cualquier dispositivo**: funciona en computadora, tablet y celular.

## 🚀 Cómo empezar

1. Abre Kiwi.ia en tu navegador.
2. Crea tu cuenta o entra con Google o Apple.
3. Escribe tu pregunta o elige una sugerencia… ¡y listo!

## 🛠️ Hecho con

| | |
|---|---|
| 🤖 Inteligencia artificial | Claude (Anthropic) |
| ⚙️ Servidor | Python + FastAPI |
| 🗄️ Base de datos y cuentas | Supabase |
| 🌐 Publicación | Vercel |

---

<details>
<summary>👩‍💻 <b>Para desarrolladores: correrlo en tu computadora</b></summary>

<br>

Necesitas Python 3.12, una API key de [Anthropic](https://platform.claude.com) y un proyecto
de [Supabase](https://supabase.com) con el esquema de `supabase/migrations/` aplicado.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Crea un archivo `.env` con tus claves:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://TU_PROYECTO.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

Inicia Kiwi y abre http://127.0.0.1:8000:

```bash
.venv/bin/python main.py
```

Para correr los tests: `.venv/bin/pip install -r requirements-dev.txt` y luego `.venv/bin/pytest`.

</details>
