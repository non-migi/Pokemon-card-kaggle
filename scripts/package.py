"""[廃止] ptcglab.build に移行しました(2026-07-12のアーキテクチャ移行)。

新しい手順:
    .venv/bin/python -m ptcglab.build <agent名>     # agents/<name>.json から組立て+検証+tar
    (提出: kaggle competitions submit -c pokemon-tcg-ai-battle -f build/<name>.tar.gz -m "...")
"""

raise SystemExit(__doc__)
