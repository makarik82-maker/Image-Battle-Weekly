# .github/workflows/image-battle.yml
name: 🖼️ Image Battle Weekly

on:
  schedule:
    # Каждую пятницу в 18:00 UTC
    - cron: '0 18 * * 5'
  workflow_dispatch:  # Ручной запуск для тестирования

jobs:
  image-battle:
    runs-on: ubuntu-latest
    
    steps:
      - name: 📥 Checkout repository
        uses: actions/checkout@v4

      - name: 🐍 Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: 📦 Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: 🎨 Generate and Post Image Battle
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          UNSPLASH_ACCESS_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}
          GIGACHAT_API_KEY: ${{ secrets.GIGACHAT_API_KEY }}
          NASA_API_KEY: ${{ secrets.NASA_API_KEY }}
        run: python scripts/image_battle.py

      - name: 📝 Commit and push if images changed
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add -A
          git diff --staged --quiet || git commit -m "📸 New Image Battle: $(date +'%Y-%m-%d')"
          git push
        env:
          github_token: ${{ secrets.GITHUB_TOKEN }}
