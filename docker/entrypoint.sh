#!/bin/sh
# Konteyner girişi. İlk çalıştırmada ayarlar, terim sözlüğü ve durak kelimeler data/'ya yazılır;
# "serve" indeksi gerekirse kurar (yoksa ya da sözlük dosyası değiştiyse) ve arayüzü açar.
#   serve            arayüz (varsayılan)
#   index            indeksi yeniden kur
#   ask "…" | ask -i data/liste.xlsx   komut satırından analiz (rapor: data/out)
#   feedback         geri bildirim özetleri
#   dictionary import data/X.xlsx | dictionary export data/Y.xlsx   sözlük aktarımı
set -eu
cd /app
SETTINGS=data/settings.yaml

# Uygulamanın her dosyası data/ altında (ADR-052); eksik olan varsayılanla başlar, var olana
# dokunulmaz (ekipte düzenlenen terim sözlüğü ve durak kelimeler korunur).
for f in settings.yaml terms.jsonl stopwords.jsonl; do
  if [ ! -f "data/$f" ]; then
    cp "defaults/$f" "data/$f"
    echo "İlk çalıştırma: varsayılan data/$f yazıldı."
  fi
done

cmd=${1:-serve}
[ "$#" -gt 0 ] && shift
case "$cmd" in
  serve)
    exec python -m vsa.cli serve --host 0.0.0.0 --port "${VSA_PORT:-8765}" --auto-index \
      --settings "$SETTINGS" "$@"
    ;;
  index | ask)
    exec python -m vsa.cli "$cmd" --settings "$SETTINGS" "$@"
    ;;
  dictionary)
    sub=${1:-}
    [ "$#" -gt 0 ] && shift
    exec python -m vsa.cli dictionary "$sub" "$@" --settings "$SETTINGS"
    ;;
  feedback)
    exec python -m vsa.cli feedback --export data/golden_candidates.yaml "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
