# EasyGhost

Éditeur de cartes mentales en Python + PySide6.

    python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
    .venv/bin/python -m easyghost [fichier]   # ou : .venv/bin/easyghost
    .venv/bin/pytest

## Exemples
Le dossier `examples/` contient deux cartes SimpleMind (`.smmx`) pour essayer l'import :

    .venv/bin/python -m easyghost "examples/Plantes Potagères.smmx"

## Interface
**Barre d'outils** : Ouvrir · Enregistrer · Enregistrer sous · Fermer · Défaire · Refaire ·
**Nœud** (clic : enfant ; flèche : enfant, parent ou frère) · Supprimer (corbeille) · **Zoom** (menu de
niveaux) · Centrer (sur le nœud principal) · puis les cinq boutons de l'**Inspecteur**, à droite :

| Bouton | Contenu de l'Inspecteur |
|---|---|
| Contour | l'arborescence des nœuds en texte ; cliquer sélectionne le nœud (et déplie les branches repliées) |
| Note | la note du nœud sélectionné, modifiable |
| Couleur | palette rapide appliquée au fond, au texte, au contour ou à la branche |
| Icônes | liste d'icônes avec catégories et recherche |
| Style | police, taille, gras/italique/souligné/barré, alignement et largeur du paragraphe, forme, type et épaisseur du trait (contour et lien), couleurs |

Un second clic sur le bouton actif referme l'Inspecteur.

| Action | Raccourci |
|---|---|
| Nouvel enfant / frère / parent | Tab / Entrée / Ctrl+Entrée |
| Éditer | F2 ou double-clic (Entrée valide, Maj+Entrée = nouvelle ligne, Échap annule) |
| Supprimer | Suppr ou ⌫ (la racine est protégée ; plusieurs nœuds : une seule annulation) |
| Replier / déplier les enfants | Espace |
| Couper / copier / coller | Ctrl+X / Ctrl+C / Ctrl+V |
| Naviguer | Flèches |
| Déplacer une branche | glisser le nœud sur son nouveau parent |
| Annuler / rétablir | Ctrl+Z / Ctrl+Maj+Z |
| Zoom | Ctrl+molette, Ctrl +/−, Ctrl+0 (ajuster), Ctrl+1 (100 %) |
| Gras / italique | Ctrl+B / Ctrl+I |

Ces raccourcis sont de vraies actions du menu **Édition** (affichés par le menu système). Ils ne sont
actifs que lorsque la carte a le focus et qu'aucun texte n'est en cours d'édition : Tab, Espace, Suppr
et Entrée restent des touches de saisie normales dans une note ou un champ de l'Inspecteur.

## Clic droit sur un nœud
Le nœud cliqué est sélectionné (une multi-sélection qui le contient est conservée), puis :
- **Couper / Copier / Coller** : les sous-arbres complets (style, note, lien, icône) sont copiés ; le
  presse-papiers contient aussi le plan en texte indenté. Coller ajoute les nœuds comme enfants du nœud
  cliqué. On peut aussi coller une liste de texte (une ligne par nœud, l'indentation donne la hiérarchie,
  les puces `-`, `*`, `•` sont retirées).
- **Replier / Déplier les enfants** (selon l'état).
- **Afficher dans l'inspecteur** : Contour, Note, Couleur, Icônes ou Style, pour le nœud cliqué.

## Styles
Tous les réglages s'appliquent aux nœuds sélectionnés (Ctrl ou Maj-clic pour en choisir plusieurs).
La couleur de branche colore le lien et le contour ; ses descendants en héritent. Le menu **Style**
reprend les raccourcis principaux.

## Notes, liens, icônes
La page **Note** de l'Inspecteur montre la note du nœud sélectionné et se modifie directement
(enregistrée quand on quitte le champ, annulable).
Menu **Contenu** : *Note…* (Ctrl+Maj+N, ouvre l'Inspecteur), *Lien…* (Ctrl+K), *Icône…*.
Un nœud affiche son icône à gauche du texte et les pastilles 📝 / 🔗 à droite ; cliquer sur la
pastille ouvre la note ou le lien, et le survol affiche la note. Seuls les liens `http`, `https` et
`mailto` sont ouverts (jamais `file:`, `javascript:`…).

## Formats
| Format | Ouvrir | Exporter | Conservé |
|---|---|---|---|
| `.easyghost` (natif, JSON) | ✔ | Enregistrer | tout |
| SimpleMind `.smmx` | ✔ | ✔ | texte, hiérarchie, côtés, styles, notes, liens ; les icônes SimpleMind sont ignorées à l'import et non exportées |
| FreeMind / Freeplane `.mm` | ✔ | ✔ | idem + repli, icônes équivalentes (11) ; formes rect/losange → « bulle » |
| OPML 2.0 `.opml` | | ✔ | texte, hiérarchie, notes (`_note`), liens (`url`) |
| Markdown `.md` | | ✔ | titre + liste imbriquée, notes en citations, liens, icônes |
| XMind `.xmind` | | ✔ | hiérarchie, notes, liens, styles, repli, marqueurs équivalents |
| Image PNG / SVG / PDF | | ✔ | rendu de la carte (sans sélection) |

*Fichier ▸ Ouvrir* reconnaît les formats importables (un fichier importé est un nouveau document à
enregistrer en `.easyghost`) ; *Fichier ▸ Exporter vers* écrit les autres. Chaque import/export affiche
ce qui n'a pas pu être conservé. À l'import, les images, cases à cocher, relations et contacts sont
ignorés. Les positions libres de SimpleMind ne sont pas reprises : la carte est remise en page.

## Icônes et licences
Les 90 icônes intégrées viennent de [Lucide](https://lucide.dev) (licence ISC, texte dans
`easyghost/icons/LICENSE-lucide.txt`). Les icônes d'un fichier SimpleMind ne sont pas reprises à l'import
(un message le signale) et EasyGhost n'en écrit pas à l'export.

## Icône de l'application
`easyghost/icons/AppIcon.icns` est un dessin original (fantôme et branches de carte mentale, palette violet/indigo),
généré par `tools/make_icon.py`. Les couleurs sont en tête du script :
`.venv/bin/python tools/make_icon.py` régénère le fichier après modification.

## Application macOS (EasyGhost.app)
    .venv/bin/pip install -e '.[build]'      # une fois : installe PyInstaller
    tools/build_macos.sh                     # produit dist/EasyGhost.app et dist/EasyGhost-<version>.dmg

Le script construit l'application avec PyInstaller (`packaging/easyghost.spec`), la vérifie
(`EasyGhost --self-check` : icônes, exports, formats, fenêtre) puis prépare l'image disque, avec un raccourci
vers « Applications ». L'application déclare les types `.easyghost` (par défaut), `.smmx` et `.mm` : un
double-clic ou un glisser sur l'icône du Dock ouvre le fichier.

- Le paquet est pour l'architecture de la machine qui le construit (arm64 ici) et signé « ad hoc » :
  il se lance sur cette machine ; sur un autre Mac, Gatekeeper demandera une confirmation
  (clic droit ▸ Ouvrir). Une distribution large demande un compte développeur Apple (signature et notarisation).
- Le numéro de version vient de `pyproject.toml`.
