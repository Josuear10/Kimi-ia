# Kiwi.ia

Kiwi.ia es un asistente conversacional web impulsado por **Claude Opus 5.5**. Cada persona
inicia sesión con su cuenta, conversa con Kiwi y encuentra su historial guardado para
retomar cualquier conversación donde la dejó: Kiwi recuerda el contexto de los mensajes
anteriores.

## Funcionalidades

- **Chat con IA**: respuestas de Claude Opus 5.5 con formato (negritas, listas, tablas, código)
  renderizado de forma segura.
- **Cuentas de usuario**: registro e inicio de sesión con correo y contraseña, y con Google o
  Apple cuando están habilitados en Supabase.
- **Historial de conversaciones**: lista de chats, abrir uno anterior, continuar la conversación
  con memoria del contexto y eliminarla.
- **Privacidad por diseño**: cada usuario solo puede ver sus propias conversaciones; lo garantiza
  la base de datos con Row Level Security.
- **Interfaz responsive** basada en el design system *Crypto Blue* (DM Sans + JetBrains Mono).

## Tecnologías

| Capa | Tecnología |
|---|---|
| Modelo de IA | [Claude Opus 5.5](https://platform.claude.com) vía el SDK oficial `anthropic` |
| Backend | Python 3.12 · [FastAPI](https://fastapi.tiangolo.com) · Uvicorn · httpx |
| Base de datos | [Supabase](https://supabase.com) (PostgreSQL + Row Level Security) |
| Autenticación | Supabase Auth (email/contraseña, Google, Apple) |
| Frontend | HTML, CSS y JavaScript sin framework · `supabase-js` · `marked` + `DOMPurify` |
| Despliegue | [Vercel](https://vercel.com) |
| Calidad | pytest · Ruff (lint y formato) · mypy (modo estricto) |

## Arquitectura

```
Navegador ──login──► Supabase Auth ──► access token (JWT)
Navegador ──token──► FastAPI /api/* ──mismo token──► Supabase PostgREST (RLS)
                          └──────────────────────────► Anthropic (Claude Opus 5.5)
```

El backend no usa claves administrativas de Supabase: cada consulta viaja con el token del
propio usuario, así que las políticas RLS de Postgres son la capa de autorización.

El código se organiza en capas con dependencias en una sola dirección:

```
app.py                     Capa HTTP: autenticación, validación, rutas y errores
config.py                  Configuración leída del entorno
errors.py                  Errores con mensajes seguros para el usuario
services/conversations.py  Casos de uso del chat (sin dependencias de infraestructura)
services/llm.py            Adaptador de Anthropic
services/supabase.py       Adaptador de Supabase (Auth + PostgREST)
public/index.html          Frontend
supabase/migrations/       Esquema de la base de datos
tests/                     Tests unitarios y de API
main.py                    Servidor de desarrollo local
```

## Base de datos

Dos tablas en el esquema `public`, ambas con Row Level Security:

- **`conversations`**: un hilo de chat por usuario (`id`, `user_id`, `title`, `created_at`, `updated_at`).
- **`messages`**: mensajes del hilo, solo se agregan (`role` = `user` | `assistant`, `content`, `model`).

El dueño de cada fila lo asigna la base (`auth.uid()`), una clave foránea compuesta impide
escribir en conversaciones ajenas y los mensajes se eliminan junto con su conversación.
El script completo está en `supabase/migrations/`.

## Puesta en marcha local

Requisitos: Python 3.12, una API key de Anthropic y un proyecto de Supabase con la migración
de `supabase/migrations/` aplicada.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://TU_PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

> Usa la *publishable* (o *anon*) key de Supabase, nunca la *secret* / *service_role*.
> `.env` está en `.gitignore`: no lo subas al repositorio.

Inicia el servidor y abre http://127.0.0.1:8000:

```bash
.venv/bin/python main.py
```

## Tests y calidad

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app.py main.py config.py errors.py services tests
```

## API

Todas las rutas, salvo `/api/config`, requieren `Authorization: Bearer <access token de Supabase>`.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/config` | URL y publishable key de Supabase para el navegador |
| `POST` | `/api/chat` | Envía `{prompt, conversation_id?}`; responde `{response, conversation_id}` |
| `GET` | `/api/conversations` | Conversaciones del usuario, la más reciente primero |
| `GET` | `/api/conversations/{id}/messages` | Mensajes de una conversación en orden |
| `DELETE` | `/api/conversations/{id}` | Elimina una conversación y sus mensajes |

## Despliegue

Kiwi.ia se despliega en Vercel desde este repositorio: Vercel ejecuta `app.py` como función
de Python y sirve `public/` desde su CDN. Configura en el proyecto de Vercel las mismas
variables de entorno del `.env` y agrega la URL de producción en Supabase →
*Authentication → URL Configuration*.
