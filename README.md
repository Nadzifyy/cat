# Cat Platformer

A 2D platformer game featuring a cat as the playable character, built with Python and Pygame.

## Play Locally (Desktop)

```bash
pip install pygame
python main.py
```

## Controls

| Action       | Keys                    |
|--------------|-------------------------|
| Move         | A / D or Arrow keys     |
| Jump         | Space / W / Up          |
| Double Jump  | Press jump again midair |
| Pause        | ESC                     |
| Skin Shop    | S (on menu)             |
| Retry        | R (on game over)        |
| Menu         | M (on game over)        |

## Deploy to the Web (Render)

### Option 1 — Render Dashboard

1. Push this repo to GitHub.
2. Go to [Render](https://render.com) → **New** → **Static Site**.
3. Connect your GitHub repo.
4. Set these values:
   - **Build Command:** `pip install pygbag && python -m pygbag --build .`
   - **Publish Directory:** `build/web`
5. Click **Create Static Site**. Done!

### Option 2 — render.yaml (Blueprint)

This repo includes a `render.yaml`. On Render, go to **Blueprints** → connect the repo and it auto-configures.

### Option 3 — Build Locally, Deploy Anywhere

```bash
pip install pygbag
python -m pygbag --build .
```

This generates a `build/web/` folder containing static HTML/JS/WASM files. Upload that folder to any static host (Render, Netlify, GitHub Pages, Vercel, etc.).

## Test Web Build Locally

```bash
pip install pygbag
python -m pygbag .
```

Then open `http://localhost:8000` in your browser.
