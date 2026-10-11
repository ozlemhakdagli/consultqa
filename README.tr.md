# consultqa

[English](README.md) | **Türkçe**

consultqa, yüklediğiniz belgelerde soru sormanızı ve cevabı geldiği kaynak metinle birlikte görmenizi sağlar. Sayfa Türkçe ve İngilizce kullanılabilir; belgeler ve sorular da bu iki dilden biri olabilir. Her şey Docker ile kendi bilgisayarınızda çalışır. Harici bir LLM uç noktası yapılandırmadığınız sürece belgeleriniz bilgisayarınızdan çıkmaz.

Ölçüm sonuçları, yayımlanan yöntemle karşılaştırma ve ayrıntılı tablolar [README.md](README.md) dosyasındadır (İngilizce). Bu dosya kullanım kılavuzudur.

## Durum

- Ölçümler yalnızca Türkçe, sentetik bir örnek veri üzerinde yapıldı. Hibrit arama (L2), yayımlanan yöntemin yeniden çalıştırılmasına (L0) göre belirgin biçimde daha iyidir; sonraki aşamalar (yeniden sıralama, komşu bölümler, kanıt grafı) L2'yi geçmedi. Sayılar için [README.md](README.md) dosyasına bakın.
- İngilizce desteği vardır ancak ölçülmedi: İngilizce belge ve sorular için bir kalite sayısı yoktur.
- Cevaplar belgeden seçilen kısa kesitlerdir. Yapay zekâ (LLM) ile cevap yazma bağlı değildir ve ölçülmedi.

## Hızlı başlangıç (Docker)

Docker ve Compose, yaklaşık 12 GB boş disk ve sabitlenmiş dört model gerekir. İlk açılış birkaç dakika sürer: imaj CPU için PyTorch kurar ve servis, `/api/ready` 200 dönmeden önce modelleri yükler.

Modeller `src/consultqa/config.py` içindeki (`MODEL_PINS`) sürümlerdir. Hugging Face önbelleğinizde (`~/.cache/huggingface/hub`) varsa yeniden indirmek yerine `models` birimine kopyalayın:

```bash
# 1. Build the image
docker compose build app

# 2. Copy the four cached models into the models volume (skip if you use step 2b)
MODELS="models--BAAI--bge-m3 models--BAAI--bge-reranker-v2-m3 models--deepset--xlm-roberta-large-squad2 models--sentence-transformers--multi-qa-mpnet-base-dot-v1"
docker compose --profile setup run --rm --no-deps -v "$HOME/.cache/huggingface/hub:/src:ro" \
  --entrypoint sh fetch-models -c "mkdir -p /models/hub && for m in $MODELS; do cp -r /src/\$m /models/hub/; done"

# 2b. Without a cache, download the same revisions into the volume (about 9 GB)
#     docker compose --profile setup run --rm fetch-models

# 3. Start the app and Qdrant; --wait returns when the app is healthy
CONSULTQA_BACKEND=real docker compose up -d --wait app
```

Sonra **http://127.0.0.1:8000/** adresini açın. Modelleri indirmeden denemek için `make smoke` komutunu çalıştırın.

## Sayfayı kullanma

Sayfa iki dilde çalışır. Tarayıcınızın dili Türkçe ise Türkçe, değilse İngilizce açılır. Üst çubuktaki “Dil” anahtarı (Türkçe / English) dili değiştirir; seçiminiz tarayıcıda saklanır. Sayfa üç adımdan oluşur:

1. **Belgelerinizi ekleyin.** Dosyaları alana sürükleyin ya da seçin. Her dosyanın durumu görünür: yükleniyor, hazırlanıyor, hazır ya da hata.
2. **Sorunuzu yazın.** Kendi cümlelerinizle sorun. Örnek sorular tek tıkla gelir.
3. **Cevap.** Cevap, geldiği belge ve bölümle birlikte görünür. Kaynak metnin tamamı gösterilir, cevabı içeren cümle işaretlenir.

Sayfa tek bir varsayılan klasör kullanır; Türkçe sayfada “Belgelerim”, İngilizce sayfada “My documents” adıyla görünür ve ilk ziyaretinizde oluşturulur. Veride her iki dilde de `Belgelerim` adıyla saklanır; bu yüzden dili değiştirmek ikinci bir klasör oluşturmaz. Diğer klasörler ve önerilenin dışındaki cevap yöntemleri “Gelişmiş seçenekler” altındadır (kapalı gelir). Tema anahtarı (Otomatik, Açık, Koyu) tarayıcıda saklanır.

Cevap belgenizin tek bir kesitinden alınır, bu yüzden kısa olabilir; sayfa bunu söyler ve kaynak metni her zaman gösterir.

## Diller

- **Sayfa** Türkçe ve İngilizcedir. Sayfa, dilini API'ye göndermez; API yalnızca kodlar döndürür.
- **Belge ve cevap dili.** Cevap belgenizden alınır; İngilizce belge İngilizce, Türkçe belge Türkçe cevap verir. Sayfa yalnızca cevabın çevresindeki sözleri çevirir.
- **Anahtar kelime araması.** Türkçe küçük harfe çevirme `I` harfini `ı` yapar; bu, İngilizce metinde “Invoices” ile “invoice” kelimelerinin eşleşmesini engellerdi. Türkçe harf (`ç ğ ı ö ş ü İ`) içermeyen belgeler için servis varsayılan kuralı kullanır. Türkçe harf içeren belgeler eskisi gibi işlenir; ölçüm kodu bu seçeneği kullanmaz.
- **Ölçülmedi.** Değerlendirme verisi yalnızca Türkçedir; İngilizce için kalite sayısı yoktur.

## API

Her şey `/api` altındadır; sayfa aynı uç noktaları kullanır. Hatalar `{"detail": "<kod>"}` biçimindedir (örneğin `not_ready`, `busy`, `llm_unavailable`); cümle değil kod döner.

```bash
# 1. Create a library (collection); the response holds its id
curl -s -X POST http://127.0.0.1:8000/api/collections \
  -H 'Content-Type: application/json' -d '{"name": "demo"}'

# 2. Upload a .pdf, .txt or .md file; ingestion runs as a job (503 not_ready until the models load)
curl -s -X POST http://127.0.0.1:8000/api/collections/<collection_id>/documents -F 'file=@manual.pdf'
curl -s http://127.0.0.1:8000/api/jobs/<job_id>      # state becomes done, or failed with an error code

# 3. Ask; the answer carries numbered citations and the retrieval trace
curl -s -X POST http://127.0.0.1:8000/api/collections/<collection_id>/ask \
  -H 'Content-Type: application/json' -d '{"question": "<your question>", "preset": "L2"}'
```

## Sınırlar

- Örnek veri sentetiktir ve şablona dayanır; gerçek kullanıcı sorularını ölçmez.
- Cevaplar çıkarımsaldır: bir kesit alınır, özetlenmez ya da birleştirilmez.
- Taranmış sayfalar ve karmaşık düzenler denenmedi.
- LLM ile cevap yazma yoktur, ölçülmedi ve onaylı bir varsayılanı yoktur.

## Gizlilik

Özel malzeme (`private/` klasörü ve `data/raw/`) hiçbir zaman izlenmez, Docker imajına kopyalanmaz ve yayımlanmaz.

## Testler

`make test`, `make lint`, `make privacy`. Tarayıcı testleri için `pip install -e ".[e2e]"` ve Google Chrome gerekir, sonra `pytest -m e2e`.

## Lisans

Apache-2.0, bkz. [LICENSE](LICENSE) ve [NOTICE](NOTICE). PDF ayrıştırıcısı Docling'dir (MIT). Model ağırlıkları ayrı indirilir ve kendi lisanslarını korur.
