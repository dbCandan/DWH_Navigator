#!/bin/sh
# Konteyner girişi. İlk çalıştırmada /app/data/settings.yaml varsayılanlarla oluşturulur;
# "serve" indeksi gerekirse kurar (yoksa ya da sözlük dosyası değiştiyse) ve arayüzü açar.
#   serve            arayüz (varsayılan)
#   index            indeksi yeniden kur
#   ask "…" | ask -i data/liste.xlsx   komut satırından analiz (rapor: data/out)
#   feedback         geri bildirim özetleri
set -eu
cd /app
SETTINGS=data/settings.yaml

if [ ! -f "$SETTINGS" ]; then
  cp docker/settings.yaml "$SETTINGS"
  echo "İlk çalıştırma: varsayılan ayarlar $SETTINGS dosyasına yazıldı."
fi

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
  feedback)
    exec python -m vsa.cli feedback --export data/golden_candidates.yaml "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
