"""公式PDF(Card_ID List_JP.pdf)からカード画像を抽出する。

目次ページの「券面画像」リンク(カードID順)→ 画像ページ → data/card_images/<id>.jpg

⚠ ライセンス注意: カード画像はコンペ限定利用の「Pokémon Elements」。
   data/ はgit管理外であり、生成物(リプレイHTML含む)を公開・再配布しないこと。
   WriteupにはめないことすKaggleの規約で失格対象と明記されている。

使い方:
    .venv/bin/python scripts/extract_card_images.py [--width 240]
"""

import argparse
import io
import os
import re
import sys

import fitz
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "data/strategy/Card_ID List_JP.pdf")
OUT = os.path.join(ROOT, "data/card_images")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=240, help="保存する画像の幅(px)")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    doc = fitz.open(PDF)

    # 目次ページを順に走査: 行のカードID列と「券面画像」リンクの対応を作る
    id_to_page = {}
    for pno in range(len(doc)):
        page = doc[pno]
        links = [l for l in page.get_links() if l.get("kind") == 1 and "page" in l]
        if not links:
            if id_to_page:
                break  # 目次の終端
            continue
        # リンクのy座標順に並べ、同ページのテキスト行からID列を取る
        links.sort(key=lambda l: l["from"].y0)
        rows = []
        for line in page.get_text().split("\n"):
            m = re.match(r"^(\d{1,4})$", line.strip())
            if m:
                rows.append(int(m.group(1)))
        # 行数とリンク数は一致するはず(多少ズレたら少ない方に合わせる)
        for cid, l in zip(rows, links):
            id_to_page[cid] = l["page"]
    print(f"目次から {len(id_to_page)} 件のID→ページ対応を取得")

    n_saved = 0
    for cid, pno in sorted(id_to_page.items()):
        out_path = os.path.join(OUT, f"{cid}.jpg")
        if os.path.exists(out_path):
            n_saved += 1
            continue
        try:
            imgs = doc[pno].get_images(full=True)
            if not imgs:
                continue
            data = doc.extract_image(imgs[0][0])
            im = Image.open(io.BytesIO(data["image"])).convert("RGB")
            ratio = args.width / im.width
            im = im.resize((args.width, int(im.height * ratio)), Image.LANCZOS)
            im.save(out_path, "JPEG", quality=82)
            n_saved += 1
        except Exception as e:
            print(f"  ID {cid}: 失敗 {e}")
    print(f"保存: {n_saved}枚 -> {OUT}")


if __name__ == "__main__":
    main()
