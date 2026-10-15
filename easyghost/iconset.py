"""Catalogue des icônes de nœud (sans dépendance à Qt).

Chaque entrée : clé -> (fichier Lucide, libellé, catégorie, emoji de secours).
Les clés historiques (idea, star, check…) sont conservées pour que les anciens fichiers
restent valides ; l'emoji sert à l'export texte (Markdown) et aux cas sans rendu SVG.
"""

from __future__ import annotations

# (clé, fichier svg, libellé, catégorie, emoji)
ICON_TABLE = [
    # --- Général
    ("star", "star", "Étoile", "Général", "⭐"),
    ("heart", "heart", "Cœur", "Général", "❤️"),
    ("flag", "flag", "Drapeau", "Général", "🚩"),
    ("bookmark", "bookmark", "Marque-page", "Général", "🔖"),
    ("pin", "pin", "Épingle", "Général", "📌"),
    ("tag", "tag", "Étiquette", "Général", "🏷️"),
    ("gift", "gift", "Cadeau", "Général", "🎁"),
    ("crown", "crown", "Couronne", "Général", "👑"),
    ("trophy", "trophy", "Trophée", "Général", "🏆"),
    ("award", "award", "Récompense", "Général", "🏅"),
    ("zap", "zap", "Éclair", "Général", "⚡"),
    ("flame", "flame", "Flamme", "Général", "🔥"),
    ("rocket", "rocket", "Fusée", "Général", "🚀"),
    ("target", "target", "Cible", "Général", "🎯"),
    ("sun", "sun", "Soleil", "Général", "☀️"),
    ("moon", "moon", "Lune", "Général", "🌙"),
    ("cloud", "cloud", "Nuage", "Général", "☁️"),
    ("umbrella", "umbrella", "Parapluie", "Général", "☂️"),
    # --- Statut
    ("check", "circle-check", "Fait", "Statut", "✅"),
    ("cross", "circle-x", "Refusé", "Statut", "❌"),
    ("warning", "triangle-alert", "Attention", "Statut", "⚠️"),
    ("important", "circle-alert", "Important", "Statut", "❗"),
    ("question", "circle-help", "Question", "Statut", "❓"),
    ("info", "info", "Information", "Statut", "ℹ️"),
    ("idea", "lightbulb", "Idée", "Statut", "💡"),
    ("bell", "bell", "Cloche", "Statut", "🔔"),
    ("thumbs-up", "thumbs-up", "Pouce levé", "Statut", "👍"),
    ("thumbs-down", "thumbs-down", "Pouce baissé", "Statut", "👎"),
    ("ban", "ban", "Interdit", "Statut", "🚫"),
    ("hourglass", "hourglass", "Sablier", "Statut", "⏳"),
    # --- Communication
    ("user", "user", "Personne", "Communication", "👤"),
    ("users", "users", "Groupe", "Communication", "👥"),
    ("mail", "mail", "Message", "Communication", "✉️"),
    ("phone", "phone", "Téléphone", "Communication", "📞"),
    ("chat", "message-circle", "Discussion", "Communication", "💬"),
    ("globe", "globe", "Web", "Communication", "🌐"),
    ("link", "link", "Lien", "Communication", "🔗"),
    ("at-sign", "at-sign", "Arobase", "Communication", "@"),
    ("megaphone", "megaphone", "Annonce", "Communication", "📣"),
    ("share", "share-2", "Partager", "Communication", "📤"),
    ("send", "send", "Envoyer", "Communication", "📨"),
    # --- Travail
    ("calendar", "calendar", "Calendrier", "Travail", "📅"),
    ("clock", "clock", "Horloge", "Travail", "🕐"),
    ("briefcase", "briefcase", "Mallette", "Travail", "💼"),
    ("folder", "folder", "Dossier", "Travail", "📁"),
    ("file", "file-text", "Document", "Travail", "📄"),
    ("book", "book-open", "Livre", "Travail", "📖"),
    ("pencil", "pencil", "Crayon", "Travail", "✏️"),
    ("list", "clipboard-list", "Liste", "Travail", "📋"),
    ("chart", "chart-bar", "Graphique", "Travail", "📊"),
    ("trend", "trending-up", "Progression", "Travail", "📈"),
    ("money", "dollar-sign", "Argent", "Travail", "💲"),
    ("euro", "euro", "Euro", "Travail", "💶"),
    ("cart", "shopping-cart", "Panier", "Travail", "🛒"),
    ("tool", "wrench", "Outil", "Travail", "🔧"),
    ("settings", "settings", "Réglages", "Travail", "⚙️"),
    ("key", "key", "Clé", "Travail", "🔑"),
    ("lock", "lock", "Cadenas", "Travail", "🔒"),
    ("shield", "shield", "Bouclier", "Travail", "🛡️"),
    ("search", "search", "Recherche", "Travail", "🔍"),
    ("home", "house", "Maison", "Travail", "🏠"),
    ("building", "building-2", "Bâtiment", "Travail", "🏢"),
    ("school", "graduation-cap", "Études", "Travail", "🎓"),
    # --- Nature
    ("leaf", "leaf", "Feuille", "Nature", "🍃"),
    ("flower", "flower-2", "Fleur", "Nature", "🌸"),
    ("tree", "tree-pine", "Arbre", "Nature", "🌲"),
    ("sprout", "sprout", "Pousse", "Nature", "🌱"),
    ("water", "droplet", "Goutte", "Nature", "💧"),
    ("apple", "apple", "Pomme", "Nature", "🍎"),
    ("carrot", "carrot", "Carotte", "Nature", "🥕"),
    ("coffee", "coffee", "Café", "Nature", "☕"),
    ("food", "utensils", "Repas", "Nature", "🍴"),
    ("bug", "bug", "Insecte", "Nature", "🐛"),
    ("paw", "paw-print", "Patte", "Nature", "🐾"),
    ("fish", "fish", "Poisson", "Nature", "🐟"),
    ("cat", "cat", "Chat", "Nature", "🐱"),
    ("dog", "dog", "Chien", "Nature", "🐶"),
    # --- Voyage et loisirs
    ("plane", "plane", "Avion", "Voyage et loisirs", "✈️"),
    ("car", "car", "Voiture", "Voyage et loisirs", "🚗"),
    ("bike", "bike", "Vélo", "Voyage et loisirs", "🚲"),
    ("map", "map", "Carte", "Voyage et loisirs", "🗺️"),
    ("place", "map-pin", "Lieu", "Voyage et loisirs", "📍"),
    ("compass", "compass", "Boussole", "Voyage et loisirs", "🧭"),
    ("tent", "tent", "Tente", "Voyage et loisirs", "⛺"),
    ("mountain", "mountain", "Montagne", "Voyage et loisirs", "⛰️"),
    ("camera", "camera", "Appareil photo", "Voyage et loisirs", "📷"),
    ("music", "music", "Musique", "Voyage et loisirs", "🎵"),
    ("game", "gamepad-2", "Jeu", "Voyage et loisirs", "🎮"),
    ("smile", "smile", "Sourire", "Voyage et loisirs", "😊"),
    ("frown", "frown", "Triste", "Voyage et loisirs", "🙁"),
]

CATEGORIES = list(dict.fromkeys(row[3] for row in ICON_TABLE))

# icônes de l'interface (barres d'outils, panneaux)
UI_ICONS = [
    "folder-open", "save", "file-down", "x", "undo-2", "redo-2", "plus", "trash-2", "zoom-in",
    "locate-fixed", "list-tree", "sticky-note", "palette", "smile", "paintbrush",
    "align-left", "align-center", "align-right", "chevron-down", "corner-left-up",
    "corner-right-down", "git-branch", "minus", "rotate-ccw", "search",
]
