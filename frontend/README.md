# AI Personal Assistant Frontend

React and Vite client for the AI assistant dashboard, including chat, tasks, calendar views, and authentication flows.

> Central documentation: see [../README.md](../README.md). This file focuses on frontend-specific details.

## Overview

The frontend provides:

- Conversational chat interface with assistant responses
- Dashboard widgets for tasks and schedule visibility
- OAuth-aware login and session handling
- Responsive experience across desktop and mobile

## Technology Stack

- React 18
- Vite 5
- Tailwind CSS 3
- Nginx (containerized static serving)

## Project Structure

```text
frontend/
	src/
		components/        # UI components (chat, widgets, auth, layout)
		lib/               # API client and helper utilities
		App.jsx            # Application root
		main.jsx           # React entry point
		index.css          # Global styles and Tailwind layers
	index.html
	vite.config.js
	tailwind.config.js
	postcss.config.js
	nginx.conf
	default.conf
```

## Local Development

Install dependencies and run the dev server from the frontend folder:

```bash
cd frontend
npm install
npm run dev
```

By default, Vite serves the app on localhost and proxies API calls to the backend target configured in [vite.config.js](vite.config.js).

## Build and Preview

```bash
cd frontend
npm run build
npm run preview
```

Build artifacts are generated in `dist/`.

## Available Scripts

- `npm run dev` - start local development server
- `npm run build` - create production build
- `npm run preview` - preview the production build locally
- `npm run lint` - run lint checks

## Backend Integration

- Frontend requests use `/api/v1/...` endpoints.
- In development, requests are proxied by Vite.
- In containerized deployment, Nginx configuration routes static assets and API traffic.

## Deployment Notes

For Docker-based deployment, use the included Dockerfile and Nginx configs.

```bash
cd frontend
docker build -t ai-assistant-frontend:latest .
docker run -p 3000:80 ai-assistant-frontend:latest
```

Ensure backend base URLs and CORS settings are aligned for the target environment.

For the integrated stack from the workspace root:

```bash
docker compose up -d --build postgres redis backend frontend
```

Then open http://localhost:3000.

## Troubleshooting

- Dependency install issues: remove `node_modules` and `package-lock.json`, then reinstall.
- API connectivity issues: confirm backend is running and proxy configuration is correct.
- Blank page after deploy: verify static serving path and Nginx configuration.
- CORS failures: align backend allowed origins with frontend domain and protocol.

## Related Documentation

- [../FRONTEND_TOOLS_INTEGRATION.md](../FRONTEND_TOOLS_INTEGRATION.md)
- [../TESTING_QUICKSTART.md](../TESTING_QUICKSTART.md)
- [../DEPLOYMENT_READINESS.md](../DEPLOYMENT_READINESS.md)
