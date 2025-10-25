# Shopify Autoimport

Dette prosjektet inneholder "Fiske & Jakt AutoImporter Codex" – et lite rammeverk for å importere og synkronisere produkter fra en Shopify-CSV-fil.

## Kom i gang

1. Opprett og aktiver et virtuelt miljø (valgfritt):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Installer avhengigheter:

   ```bash
   pip install -r requirements.txt
   ```

3. Oppdater `autoimport_codex/config/codex.yaml` med Shopify-URL og API-nøkkel.

4. Kjør hele pipelinen mot en eksportert Shopify-CSV:

   ```bash
   python -m autoimport_codex path/til/produkter.csv
   ```

   Standard er "dry-run" (ingen endringer i Shopify). Legg til `--apply` for å gjøre faktiske API-kall og `--update-cache` for å oppdatere `data/cache_inventory.csv` etter en vellykket kjøring.

5. Eventuelle nye produkter blir skrevet til `autoimport_codex/data/new_products.json`. Du kan opprette disse via:

   ```bash
   python autoimport_codex/engine/product_creator.py -- (dry-run som standard)
   ```

## Nyttige flagg

```bash
python -m autoimport_codex produkter.csv --apply --update-cache
python -m autoimport_codex produkter.csv --delimiter ';' --no-new-products-file
```

Se `python -m autoimport_codex --help` for full oversikt.