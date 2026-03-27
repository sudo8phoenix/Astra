# AI Personal Assistant Dashboard — Frontend

React + Tailwind CSS UI for the AI Personal Assistant.

## 📋 Features

- ✅ **Design System**: Glassmorphism, gradients, and glow effects
- ✅ **Responsive Layout**: Mobile-first, adapts to all screen sizes
- ✅ **Semantic HTML**: Proper ARIA labels and accessibility landmarks
- ✅ **Chat Panel**: Real-time messaging with AI responses
- ✅ **Dashboard Widgets**: Tasks, Calendar, Activity tracking
- ✅ **Dark Mode**: Built-in dark theme with custom color tokens

## 🚀 Quick Start

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

Visit `http://localhost:3000`

### Build

```bash
npm run build
```

## 📁 Project Structure

```
frontend/
├── public/                 # Static assets
├── src/
│   ├── components/
│   │   ├── Layout.jsx      # Main layout wrapper
│   │   ├── Sidebar.jsx     # Navigation sidebar
│   │   ├── ChatPanel.jsx   # Chat interface
│   │   ├── WidgetsRegion.jsx # Dashboard widgets container
│   │   ├── TasksWidget.jsx # Task list widget
│   │   ├── CalendarWidget.jsx # Daily schedule
│   │   └── ActivityWidget.jsx # Metrics/insights
│   ├── App.jsx             # Root component
│   ├── main.jsx            # Entry point
│   └── index.css           # Global styles + Tailwind
├── index.html              # HTML entry
├── tailwind.config.js      # Design tokens & theme
├── vite.config.js          # Vite config
├── postcss.config.js       # PostCSS config
└── package.json
```

## 🎨 Design Tokens

### Colors
- **Primary**: `#6C63FF` (Purple)
- **Secondary**: `#00D4FF` (Cyan)
- **Background**: `#0F172A` (Dark Blue)
- **Text Primary**: `#FFFFFF` (White)
- **Text Secondary**: `#94A3B8` (Gray)

### Typography
- **H1**: 28px
- **H2**: 20px
- **Body**: 14px

### Spacing
- Grid: 12-column
- Base unit: 16px
- Card padding: 16–24px

### Border Radius
- Small: 8px
- Medium: 12px
- Large: 16px
- Extra Large: 24px

## ♿ Accessibility

- ✅ Semantic HTML (`<nav>`, `<main>`, `<section>`, `<article>`)
- ✅ ARIA labels for dynamic content
- ✅ Keyboard navigation support
- ✅ Focus-visible states
- ✅ High contrast text
- ✅ `prefers-reduced-motion` support
- ✅ Proper alt text and labels

## 📱 Responsive Breakpoints

- **Mobile**: < 640px (Single column)
- **Tablet**: 640px–1024px (2 columns)
- **Desktop**: > 1024px (3 columns + sidebar fixed)

## 🔌 API Integration

Frontend connects to backend via:

```
/api/v1/...
```

Configured in `vite.config.js` with proxy to `http://localhost:8000`

## 📦 Dependencies

- **React 18**: UI library
- **Tailwind CSS 3**: Styling framework
- **Vite 5**: Build tool

## 🛠️ Scripts

```bash
npm run dev      # Start development server
npm run build    # Build for production
npm run preview  # Preview production build
npm run lint     # Run ESLint
```

## 🚀 Deployment

```bash
# Build static assets
npm run build
```

- The production build output is generated in `dist/`.
- Serve `dist/` behind Nginx (see `nginx.conf` and `default.conf`).
- Ensure API proxy/target points to the correct backend host in your environment.

## 🆘 Troubleshooting

- `npm install` fails: remove `node_modules` and `package-lock.json`, then reinstall.
- Frontend cannot reach backend: verify backend is running and proxy target is correct.
- Blank page in production: confirm static files are served from `dist/` and fallback routing is configured.
- CORS errors: align backend allowed origins with the frontend domain.

## 🔄 Next Steps (Integration Gate 1)

- [ ] Define API DTOs for chat, task, calendar, email
- [ ] Connect ChatPanel to backend WebSocket
- [ ] Implement real-time widget updates
- [ ] Add sample data fetching from `/api/v1/`

## Repository Tracking Policy

This repository currently ignores most auxiliary artifacts at the root policy level:
- Markdown files except `README.md`/`readme.md`
- Shell scripts (`*.sh`)
- YAML files (`*.yml`, `*.yaml`)
- `SETUP_SCRIPTS/`
