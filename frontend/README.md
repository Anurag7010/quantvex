# QuantVex Frontend

React 19 / TypeScript SPA — the user interface for the QuantVex AI-powered financial intelligence platform.

## Getting Started

```bash
npm install
npm start        # dev server at http://localhost:3000
```

## Environment

Copy `.env.example` to `.env` and fill in the values:

```env
# Backend API URL — set to Render URL in production
# Production: https://quantvex-api-zpai.onrender.com
REACT_APP_API_URL=http://localhost:8000

# API key — must match MCP_API_KEY on the backend
REACT_APP_API_KEY=dev_key_change_in_production
```

## Build

```bash
npm run build    # outputs to frontend/build/
```

## Project Structure

```
src/
├── pages/           # LandingPage, ChatPage, DashboardPage, LoginPage, SignUpPage
├── components/
│   ├── analysis/    # VerdictCard, BullCaseCard, BearCaseCard, StreamingAnalysis
│   └── ui/          # AnimatedHero, AnimatedAIChat, FocusRail, shared UI primitives
├── services/
│   └── api.ts       # Typed Axios API client
├── context/
│   └── ThemeContext.tsx
└── App.tsx          # Router + ThemeProvider
```

## Live Demo

- Frontend: [quantvex.vercel.app](https://quantvex.vercel.app)
- API: [quantvex-api-zpai.onrender.com](https://quantvex-api-zpai.onrender.com)
