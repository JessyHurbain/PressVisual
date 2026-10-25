# PressVisual — visualiseur de frappes clavier et de clics souris

PressVisual est une application de bureau Python qui affiche en temps réel, dans une
petite bulle flottante, les touches que vous tapez et les clics que vous faites.
Elle est conçue pour les **captures d'écran**, les **tutoriels** et les
**formations en ligne** : l'overlay est discret, élégant, toujours au premier
plan, et n'apparaît que lorsqu'il y a quelque chose à montrer.

```
┌──────────────────────────────────┐
│  [Ctrl] + [Maj] + [P]            │
│  [b]                             │
│  [o]                             │
│  [Entrée]                        │
└──────────────────────────────────┘
```

## Fonctionnalités

- **Overlay moderne** : coins arrondis, fond sombre dégradé semi-transparent
  (type verre fumé), texte blanc contrasté, police système épurée.
- **Apparence personnalisable** : une fenêtre de réglages avec aperçu en direct
  permet de changer les couleurs, la police, l'opacité, les coins arrondis et
  les marges, puis d'enregistrer le tout dans la configuration.
- **Fenêtre sans bordure**, toujours au premier plan, déplaçable au clic-glisser.
- **Apparition immédiate**, maintien configurable (2 s par défaut), puis fondu
  de disparition.
- **Capture globale** du clavier et de la souris via `pynput`, dans un fil
  séparé : l'interface reste fluide même pendant une frappe rapide.
- **Combinaisons de touches** affichées en badges :
  `[Ctrl] + [Maj] + [P]`, `[Alt] + [Tab]`, `[Maj] + [→]`, etc.
- **Affichage touche par touche** : chaque frappe apparaît dans sa propre
  pastille (`[b]`, `[o]`, `[n]`, `[Entrée]`, `[Ctrl] + [Maj] + [P]`…), sans
  regrouper les lettres en mots. Un mode optionnel (`concat_text`) reforme le
  texte saisi sur une seule ligne si vous le préférez.
- **Pavé numérique** : chiffres `0` à `9`, opérateurs `+ - * /`, séparateur
  décimal et touche Entrée reconnus, y compris lorsque `pynput` ne fournit pas
  de caractère pour ces touches.
- **Souris** : clic gauche, clic droit, clic milieu, double-clic, triple-clic et
  molette (les crans successifs sont agrégés : `Scroll ↓ ×3`).
- **Raccourcis globaux** pour masquer l'overlay, le rendre transparent aux clics,
  masquer les frappes sensibles ou quitter.
- **Mode privé** : `Ctrl + F12` masque tout et suspend la capture ; les frappes
  ne sont ni affichées ni conservées.
- **Mode masqué** : `Ctrl + F10` remplace les caractères saisis par des puces
  (`••••••`), utile pendant la saisie d'un mot de passe.
- **Filtrage de touches** par configuration (par exemple `F12` ou
  `print_screen`).
- **Menu de notification** (system tray) : afficher/masquer, clics traversants,
  masquage, personnalisation de l'apparence, choix du coin d'ancrage, quitter.
- **Multi-écrans** : positionnement aux quatre coins (haut/bas, gauche/droite)
  ou en bas au centre, sur l'écran où se trouve le curseur.
- **Aucune donnée envoyée sur le réseau**. L'application est entièrement locale.

## Prérequis

- Python **3.9 ou plus récent** (testé avec Python 3.14.6 sous Windows 11).
- Windows 10/11, macOS 11+ ou Linux avec un serveur **X11** (Wayland : voir la
  section [Dépannage](#dépannage)).
- Les dépendances listées dans `requirements.txt` :
  - `PyQt6` (interface, animations, transparence) ;
  - `pynput` (écoute globale des entrées, multiplateforme).

## Installation

```bash
# 1. Se placer dans le dossier du projet
cd clavier

# 2. Créer un environnement virtuel
python -m venv .venv

# 3. L'activer
# Windows (PowerShell ou cmd)
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 4. Installer les dépendances
python -m pip install -r requirements.txt
```

## Lancement

```bash
python pressvisual.py
```

L'overlay reste invisible tant que vous ne tapez pas et ne cliquez pas.
L'icône PressVisual apparaît dans la zone de notification.

### Options de la ligne de commande

| Option | Description |
| --- | --- |
| `--config FICHIER` | Charge un fichier JSON de configuration. |
| `--duration SEC` | Durée de maintien après la dernière entrée (0,3 à 30 s). |
| `--opacity VALEUR` | Opacité du fond, de `0.15` à `1.0`. |
| `--font-size PT` | Taille de police (9 à 40 pt). |
| `--max-rows N` | Nombre de lignes conservées (1 à 8). |
| `--max-width PX` | Largeur maximale du contenu (220 à 1600 px). |
| `--margin PX` | Marge avec le bord de l'écran (0 à 400 px). |
| `--position POSITION` | `top-left`, `top-right`, `bottom-left`, `bottom-right` ou `bottom-center`. |
| `--no-keyboard` | N'affiche pas les frappes (les raccourcis restent actifs). |
| `--no-mouse` | N'affiche pas les clics ni la molette. |
| `--group-text` | Regroupe les caractères saisis en texte continu au lieu d'une touche par ligne. |
| `--start-hidden` | Démarre en mode privé (capture suspendue). |
| `--click-through` | Démarre en mode clics traversants. |
| `--toggle-hotkey RACCOURCI` | Modifie le raccourci afficher/masquer. |

```bash
# Exemple : bulle en bas au centre, plus grande, affichée 3 secondes
python pressvisual.py --position bottom-center --font-size 20 --duration 3

# Exemple : uniquement la souris, opacité renforcée
python pressvisual.py --no-keyboard --opacity 0.95

# Exemple : regrouper les caractères saisis en texte continu
python pressvisual.py --group-text
```

## Utilisation

### Affichage des frappes

Par défaut, l'overlay affiche **une pastille par touche**, comme un clavier
virtuel : `[b]`, `[o]`, `[n]`, `[Espace]`, `[Entrée]`, `[Maj] + [→]`. Les
caractères ne sont pas regroupés en mots : chaque frappe reste visible
individuellement pendant la durée réglée.

Pour retrouver un affichage en texte continu (`bonjour le monde`), activez
`concat_text` dans la configuration (ou lancez avec `--group-text`). Dans ce
mode, les caractères s'ajoutent à la ligne en cours et une pause de
`typing_join_delay` secondes clôt le mot.

### Positionner et déplacer l'overlay

Le menu de l'icône de notification propose un sous-menu **Position de
l'overlay** avec les quatre coins et le bas centre :

| Choix du menu | Valeur `position` |
| --- | --- |
| Haut gauche | `top-left` |
| Haut droite | `top-right` |
| Bas gauche | `bottom-left` |
| Bas droite | `bottom-right` |
| Bas centre | `bottom-center` |

La bulle se place sur l'écran où se trouve le curseur, à la distance `margin`
des bords. Elle peut aussi être déplacée librement au clic-glisser ; après un
déplacement, PressVisual conserve les bords les plus proches du centre de
l'écran, de sorte que la bulle grandisse vers le centre au fil des frappes au
lieu de sortir par un bord.

Le coin choisi dans le sous-menu est **mémorisé automatiquement** dans
`config.json` : PressVisual s'ouvre au même endroit au prochain lancement. Un
déplacement libre ne modifie pas cette préférence, qui reste le dernier coin
sélectionné. La position initiale se règle aussi avec `--position` ou la clé
`position` de `config.json`.

### Personnaliser l'apparence

Clic droit sur l'icône de notification → **Personnaliser l'overlay…** ouvre une
fenêtre de réglages avec un aperçu en direct :

- **Couleurs** : fond (haut et bas du dégradé), texte, fond et texte des
  touches, couleur d'accent des clics et des messages d'état. Les badges de
  modificateurs, les bordures et les séparateurs sont dérivés de ces couleurs
  pour rester cohérents.
- **Mise en forme** : police, taille, opacité du fond, rayon des coins, marge
  avec le bord de l'écran et largeur maximale.
- **Réinitialiser** restaure les valeurs d'origine, **Annuler** ferme sans rien
  changer et **Enregistrer** applique les réglages immédiatement puis les écrit
  dans le fichier de configuration.

Les réglages sont conservés au prochain lancement. Ils ne touchent ni au
positionnement (le dernier coin choisi reste mémorisé) ni au contenu affiché
(durée, nombre de lignes, clavier/souris).

### Raccourcis globaux

| Raccourci (par défaut) | Action |
| --- | --- |
| `Ctrl + F12` | Afficher / masquer l'overlay et suspendre la capture. |
| `Ctrl + F11` | Activer / désactiver les **clics traversants** (click-through). |
| `Ctrl + F10` | Activer / désactiver le **masquage des frappes** (`••••••`). |
| `Ctrl + F9` | Quitter PressVisual. |

Ces combinaisons fonctionnent même quand PressVisual n'a pas le focus. Elles ne sont
jamais affichées dans l'overlay. Elles sont configurables dans `config.json` et
peuvent être désactivées en mettant une chaîne vide :

```json
{
  "hotkey_toggle": "",
  "hotkey_masking": "ctrl+alt+m"
}
```

> Si un raccourci entre en conflit avec une autre application (ou avec macOS),
> remplacez-le dans la configuration. La reconnaissance est stricte : les
> modificateurs enfoncés doivent correspondre exactement.

### Clics traversants

En mode click-through, la bulle reste visible mais tous les clics la traversent :
elle ne gêne plus l'utilisation de l'application filmée. Pour la déplacer à
nouveau ou la reprendre à la souris, appuyez de nouveau sur `Ctrl + F11` (ou
utilisez le menu de l'icône de notification).

### Masquage et mode privé

- `Ctrl + F10` : les caractères saisis apparaissent sous forme de points. Les
  combinaisons de touches (`Ctrl + C`, etc.) restent visibles.
- `Ctrl + F12` : tout est masqué et la capture est suspendue. Idéal pour saisir
  des identifiants pendant une démonstration. Un nouvel appui réactive
  l'affichage.
- `filtered_keys` permet d'ignorer définitivement certaines touches.

### Zone de notification

Un clic sur l'icône affiche ou masque l'overlay. Le menu contextuel (clic droit)
donne accès à toutes les options, notamment **Quitter**. Si votre système
n'affiche pas les icônes de notification, utilisez `Ctrl + F9` (ou `Ctrl + C`
dans le terminal) pour quitter.

## Configuration

PressVisual lit un fichier `config.json` **facultatif** :

- à côté de `pressvisual.py` en exécution depuis les sources ;
- à côté de l'exécutable PyInstaller (`PressVisual.exe`) ;
- à côté du bundle `PressVisual.app` sur macOS ;
- ou n'importe où avec `--config /chemin/config.json`.

Les options de la ligne de commande sont prioritaires sur le fichier. Les clés
inconnues sont ignorées avec un avertissement, et les valeurs hors limites sont
automatiquement corrigées.

Le choix d'un coin dans le menu de l'icône met à jour la clé `position` du
fichier sans toucher aux autres clés ; si `config.json` n'existe pas encore, il
est créé. La fenêtre d'apparence enregistre de la même façon ses propres clés.
Le dossier qui contient le fichier doit donc être accessible en écriture.

### Exemple complet (valeurs par défaut)

```json
{
  "display_duration": 2.0,
  "fade_in_ms": 120,
  "fade_out_ms": 420,
  "opacity": 0.86,
  "font_family": "",
  "font_size": 16,
  "max_rows": 4,
  "max_width": 620,
  "corner_radius": 16,
  "margin": 28,
  "position": "bottom-right",
  "concat_text": false,
  "typing_join_delay": 1.1,

  "background_color": "#26282f",
  "background_color_bottom": "#0e0f12",
  "text_color": "#f6f7f9",
  "key_background_color": "#f5f6f8",
  "key_text_color": "#111216",
  "accent_color": "#548eff",

  "capture_keyboard": true,
  "capture_mouse": true,
  "ignore_key_repeats": true,
  "ignore_overlay_clicks": true,
  "filtered_keys": [],

  "ctrl_label": "Ctrl",
  "alt_label": "Alt",
  "shift_label": "Maj",
  "win_label": "Win",
  "click_left_label": "Clic gauche",
  "click_right_label": "Clic droit",
  "click_middle_label": "Clic milieu",
  "scroll_up_label": "Scroll ↑",
  "scroll_down_label": "Scroll ↓",

  "hotkey_toggle": "ctrl+f12",
  "hotkey_click_through": "ctrl+f11",
  "hotkey_masking": "ctrl+f10",
  "hotkey_quit": "ctrl+f9",

  "start_hidden": false,
  "click_through_on_start": false
}
```

### Détail des clés

| Clé | Rôle |
| --- | --- |
| `display_duration` | Secondes de maintien après la dernière entrée (0,3 à 30). |
| `fade_in_ms` / `fade_out_ms` | Durées des fondus d'apparition et de disparition. |
| `opacity` | Opacité du fond de l'overlay (0.15 à 1.0). |
| `font_family` | Police ; vide = sélection automatique (Segoe UI, SF Pro, Inter…). |
| `font_size` | Taille de police en points. |
| `max_rows` | Nombre de lignes conservées à l'écran (les plus anciennes s'effacent). |
| `max_width` | Largeur maximale du texte ; le début est tronqué avec `…`. |
| `corner_radius` | Rayon des coins de la bulle. |
| `margin` | Distance au bord de l'écran pour le positionnement initial. |
| `background_color` | Couleur du haut du dégradé de fond (format `#RRGGBB`). |
| `background_color_bottom` | Couleur du bas du dégradé de fond. |
| `text_color` | Couleur du texte, des badges de modificateurs et des bordures. |
| `key_background_color` | Fond des pastilles de touches. |
| `key_text_color` | Texte des pastilles de touches. |
| `accent_color` | Accent des clics souris, des messages d'état et de la molette. |
| `position` | `top-left`, `top-right`, `bottom-left`, `bottom-right` ou `bottom-center`. |
| `concat_text` | `false` (défaut) : une pastille par touche. `true` : les caractères s'ajoutent dans une ligne de texte. |
| `typing_join_delay` | Pause (s) qui clôt la ligne de texte en mode `concat_text`. |
| `capture_keyboard` | Afficher les frappes (les raccourcis restent actifs même si `false`). |
| `capture_mouse` | Afficher les clics et la molette. |
| `ignore_key_repeats` | Ne pas répéter une touche maintenue enfoncée. |
| `ignore_overlay_clicks` | Ne pas afficher les clics effectués sur la bulle elle-même. |
| `filtered_keys` | Jetons de touches à ignorer (`"f12"`, `"print_screen"`, `"a"`…). |
| `*_label` | Libellés des badges. Passez `shift_label` à `"Shift"` et `win_label` à `"Cmd"` pour une interface anglaise / macOS. |
| `hotkey_*` | Raccourcis globaux au format `modificateur+touche` (chaîne vide = désactivé). |
| `start_hidden` | Démarre avec la capture suspendue. |
| `click_through_on_start` | Démarre en mode clics traversants. |

### Style

La fenêtre **Personnaliser l'overlay…** couvre l'essentiel des réglages
visuels. Pour un changement plus fin, les couleurs acceptent aussi le format
`#AARRGGBB` (alpha en premier) dans le fichier de configuration ; les badges de
modificateurs, les bordures, le séparateur `+` et la couleur du texte sur les
badges d'accent sont alors recalculés à partir de ces valeurs.

Les réglages enregistrés par la fenêtre sont : `background_color`,
`background_color_bottom`, `text_color`, `key_background_color`,
`key_text_color`, `accent_color`, `opacity`, `font_family`, `font_size`,
`max_width`, `corner_radius` et `margin`.

## Empaqueter en exécutable autonome

Installation de PyInstaller :

```bash
python -m pip install pyinstaller
```

### Windows — `PressVisual.exe`

```bash
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PressVisual pressvisual.py
```

L'exécutable est créé dans `dist\PressVisual.exe` (environ 37 Mo, démarrage en
quelques secondes). `--windowed` évite l'ouverture d'une console ; l'application
se pilote par l'icône de notification et les raccourcis globaux.

Pour un démarrage plus rapide (et moins de faux positifs antivirus), préférez un
dossier autonome :

```bash
python -m PyInstaller --noconfirm --clean --onedir --windowed --name PressVisual pressvisual.py
# puis lancez dist\PressVisual\PressVisual.exe
```

Avec une icône personnalisée (fichier `.ico` ou `.icns`) :

```bash
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PressVisual --icon mon-icone.ico pressvisual.py
```

Placez `config.json` **à côté de l'exécutable** si vous voulez une configuration
persistante. Le coin choisi dans le menu y est enregistré automatiquement ; dans
un dossier protégé en écriture (`C:\Program Files`, par exemple), lancez plutôt
avec `--config "%APPDATA%\pressvisual-config.json"`.

### macOS — `PressVisual.app`

```bash
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PressVisual pressvisual.py
```

Le bundle est créé dans `dist/PressVisual.app`. Au premier lancement, macOS demande
l'autorisation de contrôler le clavier : acceptez, ou ajoutez PressVisual dans
**Réglages Système → Confidentialité et sécurité → Accessibilité**, puis
relancez l'application. Pour distribuer le bundle, signez-le et notarisez-le.

### Linux

```bash
python -m PyInstaller --noconfirm --clean --onefile --name PressVisual pressvisual.py
# puis : ./dist/PressVisual
```

`--windowed` est inutile sous Linux. Un serveur X11 (ou une session Xorg) est
nécessaire pour les raccourcis globaux. Pour un paquet distribuable, un AppImage
ou un `.deb` peuvent être construits à partir de cet exécutable.

### Notes de packaging

- Testé avec **PyInstaller 6.22.3**, PyQt6 6.11.0 et pynput 1.8.2 sous Windows 11.
- Si l'exécutable démarre mais que le clavier n'est pas capturé, forcez les
  modules de plateforme de pynput :

  ```bash
  # Windows
  python -m PyInstaller --noconfirm --clean --onefile --windowed --name PressVisual \
    --hidden-import pynput.keyboard._win32 \
    --hidden-import pynput.mouse._win32 pressvisual.py
  ```

  Sur macOS, utilisez `pynput.keyboard._darwin` et `pynput.mouse._darwin` ;
  sur Linux X11, `pynput.keyboard._xorg` et `pynput.mouse._xorg`.
- Les exécutables PyInstaller non signés peuvent déclencher SmartScreen ou un
  antivirus. C'est un faux positif lié à l'empaquetage ; signez le binaire ou
  distribuez une version `--onedir`.
- Le fichier `config.json` n'est pas embarqué automatiquement dans le binaire :
  il est lu à côté de l'exécutable au démarrage, et le menu y enregistre le
  dernier coin choisi.

## Dépannage

**Aucune bulle n'apparaît**
Vérifiez que l'icône est présente dans la zone de notification, appuyez sur
`Ctrl + F12`, puis tapez du texte. Vérifiez aussi `capture_keyboard`,
`capture_mouse`, `filtered_keys` et le mode clics traversants.

**Les raccourcis globaux ne fonctionnent pas**
Un autre logiciel (ou le système) intercepte peut-être `Ctrl + F12`. Changez
`hotkey_toggle` dans `config.json`. Sous macOS, autorisez l'application dans
**Accessibilité**.

**macOS ne capte rien**
Réglages Système → Confidentialité et sécurité → Accessibilité : ajoutez le
Terminal (si vous lancez `python pressvisual.py`) ou `PressVisual.app`, puis
quittez et relancez.

**Linux / Wayland**
Les hooks globaux de `pynput` nécessitent X11. Sous Wayland, connectez-vous à une
session « Xorg » pour un fonctionnement complet ; XWayland peut autoriser
l'affichage mais la capture globale peut être incomplète selon le compositeur.

**L'overlay n'apparaît pas dans l'enregistrement**
Utilisez une capture d'**écran** (display capture) plutôt qu'une capture de
fenêtre : l'overlay est une fenêtre séparée.

**Jeux en plein écran exclusif**
L'overlay peut ne pas s'afficher au-dessus d'un jeu en plein écran exclusif.
Utilisez le mode « fenêtré sans bordure ».

**La bulle ne se déplace plus**
Le mode clics traversants est probablement actif : `Ctrl + F11`.

**Les réglages ne sont pas mémorisés**
Le dossier de `config.json` n'est pas accessible en écriture (par exemple
`C:\Program Files`) ou le fichier contient un JSON invalide : PressVisual
fonctionne mais ne peut pas enregistrer le choix (position ou apparence).
Utilisez un dossier inscriptible avec
`--config "%APPDATA%\pressvisual-config.json"`.

**Impossible de quitter**
`Ctrl + F9`, clic droit sur l'icône → Quitter, ou `Ctrl + C` dans le terminal.

## Structure du projet

```
pressvisual.py   Application complète (interface, capture, configuration)
requirements.txt Dépendances d'exécution
README.md        Ce document
```

## Licence

Code fourni librement pour un usage personnel ou professionnel. Les polices et
bibliothèques tierces conservent leurs licences respectives.
