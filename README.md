# 🛰️ ForVis Desktop (v1.0)

**Advanced Logic Formula Visualization & Analysis Tool**

**ForVis Desktop** to zintegrowane narzędzie offline do wizualizacji i analizy złożonych formuł logicznych (**SAT** oraz **MaxSAT**). System pozwala „zobaczyć” matematyczną strukturę problemów NP-trudnych, pomagając badaczom i studentom zrozumieć, jak działają współczesne solvery.

---

## 🚀 Kluczowe Funkcje

**Analiza 360°:** 11 różnych metod wizualizacji – od klasycznych grafów interakcji po mapy ciepła i struktury hierarchiczne.


**SAT Landscape:** Unikalne rzutowanie wysokowymiarowej przestrzeni stanów na mapę 2D (PCA), pozwalające śledzić trajektorię solvera.


**Analiza What-If:** Interaktywna symulacja decyzji logicznych w trybie Side-by-Side bez modyfikowania bazowej formuły.


**Semantic Scoring:** Automatyczna identyfikacja „krytycznych” zmiennych, które generują najwięcej konfliktów w algorytmach.


**Pełna Kontrola:** Autorski mechanizm **Stop/Resume**, pozwalający pauzować ciężkie obliczenia bez zamrażania interfejsu.



---

## 🛠️ Architektura („Pod maską”)

Projekt łączy technologie webowe z wydajnością aplikacji natywnej poprzez model **Embedded Desktop**:

| Warstwa | Technologia | Rola |
| --- | --- | --- |
| **Frontend** | Angular + Electron | Interaktywny interfejs i renderowanie grafów (D3.js, Vis-network).|
| **Backend** | Django (Embedded) | Logika biznesowa, parsowanie plików DIMACS i REST API (127.0.0.1).|
| **Obliczenia** | Celery + Redis | Asynchroniczne przetwarzanie zadań w tle w trybie *Solo Pool*.|
| **Baza danych** | SQLite | Lokalny magazyn metadanych i statusów zadań.|

---

## 📉 Przykładowe Wizualizacje

System obsługuje m.in.:

1. **Interaction Graph:** Sieć powiązań między literałami.


2. **CDCL Solver Vis:** Dynamiczne drzewo decyzji pokazujące powstawanie klauzul uczących.


3. **Heatmap:** Intensywność relacji w formule.


4. **Factor Graph:** Rozszerzona reprezentacja uwzględniająca klauzule jako węzły.



---

## 💻 Instalacja i Uruchomienie

Aplikacja realizuje paradygmat **„Click & Run”** – nie wymaga instalacji Pythona, Node.js ani bazy danych.

1. Pobierz najnowszą wersję `ForVis_Setup.exe`.


2. Uruchom plik – system automatycznie powoła do życia lokalny serwer i silnik obliczeniowy.


3. Wgraj plik `.cnf` (DIMACS) i zacznij eksplorację.



---

## 🎓 Autorzy i Projekt

Projekt został zrealizowany na **Wydziale Elektrotechniki, Automatyki, Informatyki i Inżynierii Biomedycznej (EAIiIB) AGH**.

**Autorzy:** Kevin Stuka, Kalina Rączka 
**Opiekun:** dr hab. inż. Radosław Klimek 



---

**Chcesz dowiedzieć się więcej o matematyce stojącej za projektem?**
Zapoznaj się z [Pełną Dokumentacją Techniczną](https://github.com/kevooo49/ForVis-Desktop/blob/main/ForVisDesktopFinal.pdf) (Rozdział 2: Kontekst Teoretyczny).
