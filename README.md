# GEO Audit Tool – Poklemba Case Study

Toto je jednoduchý Python nástroj na audit blog článkov z pohľadu GEO (Generative Engine Optimization).
Vie načítať články z:
- mock JSON súboru
- WordPress REST API (wp-json)
- zoznamu URL

## Cieľ projektu
Vytvoriť Python nástroj, ktorý:
1) načíta články (mock JSON / WordPress REST API / zoznam URL),
2) analyzuje ich podľa 10 GEO kritérií,
3) priradí skóre (0–10),
4) vygeneruje csv aj html report s odporúčaniami,

## Vstupy, ktoré nástroj podporuje
Vie načítať články z:
- **mock JSON súboru** (`--source json`) – kontrolované testovacie dáta,
- **WordPress REST API (wp-json)** (`--source wp`) – štruktúrované dáta z API (title/content/link + meta),
- **zoznamu URL** (`--source urls`) 

## 10 GEO kritérií
1. Priama odpoveď v úvode  
2. Obsahuje definíciu  
3.  Štruktúrované nadpisy
4. Obsahuje fakty/čísla 
5. Citácie zdrojov
6. FAQ sekcia 
7. Obsahuje zoznamy 
8. Obsahuje tabuľky
9. Dostatočná dĺžka - Článok má aspoň 500 slov
10. Meta description - Meta popis existuje a má 120–160 znakov

## Výstupy
Csv a html reporty
Generujú sa do priečinka output

## Požiadavky
- Python 3.10+ (odporúčané 3.11+)
- beautifulsoup4

## Obsahuje:
- sticky header v tabuľke
- stránkovanie
- vyhľadávanie / filtrovanie
- triedenie
- farebné pásma skóre (0–4 červená, 5–7 oranžová, 8–10 zelená)

## Spustenie jednotlivých scriptov:

## Mock JSON
python -m geo_audit.main --source json --input data/articles.json --output output/report_json.csv --html output/report_json.html

## Zoznam URL
python -m geo_audit.main --source urls --input data/urls.txt --output output/report_urls.csv --html output/report_urls.html

## WordPress REST API :
python -m geo_audit.main --source wp --input "https://gymbeam.sk/blog/wp-json/wp/v2/posts?wpml_language=sk" --wp-max-pages 10 --wp-per-page 20 --wp-sleep 0.3 --output output/report_wp_sk.csv --html output/report_wp_sk.html

