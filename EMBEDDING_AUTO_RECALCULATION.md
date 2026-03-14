# Embedding Auto-Recalculation System

## Vue d'ensemble

Ce système garantit que les embeddings biométriques restent **toujours compatibles** avec la configuration actuelle du moteur de reconnaissance faciale, même lorsque celle-ci évolue (changement de `detector_backend`, `model_name`, etc.).

## Comment ça fonctionne

### 1. **Stockage de la configuration complète**

Chaque embedding stocké inclut maintenant un snapshot de la configuration utilisée:

```python
# Table: biometric_embedding
{
    "embedding": [0.234, -0.456, 0.789, ...],  # Le vecteur
    "model_name": "ArcFace",
    "provider": "deepface",
    "metadata": {                               # ← NOUVEAU
        "model_name": "ArcFace",
        "provider": "deepface",
        "detector_backend": "retinaface",
        "enforce_detection": True
    }
}
```

### 2. **Détection automatique des changements**

À chaque vérification, le système compare la configuration stockée avec la configuration actuelle:

```python
stored_config = embedding.metadata
current_config = {
    "model_name": "ArcFace",
    "provider": "deepface",
    "detector_backend": "retinaface",  # ← Maintenant
    "enforce_detection": True
}

if stored_config != current_config:
    # Configuration a changé! Recalculer automatiquement
```

### 3. **Recalcul automatique transparent**

Si la configuration a changé, l'embedding est **automatiquement recalculé** lors de la prochaine vérification:

```
Vérification #1: Config a changé
  ↓
  ⚠ Détection: opencv → retinaface
  ↓
  🔄 Recalcul automatique avec retinaface
  ↓
  ✓ Vérification utilise le nouvel embedding
  ↓
  💾 Nouvel embedding stocké

Vérification #2: Fast path (200ms)
```

### 4. **Calcul automatique après première vérification**

Pour les nouveaux insurees ou ceux sans embedding:

```
Vérification #1: Pas d'embedding
  ↓
  🐢 Slow path (2-3 secondes)
  ↓
  ✓ Vérification réussie
  ↓
  💾 Calcul et stockage automatique de l'embedding

Vérification #2: Fast path (200ms)
```

## Scénarios d'utilisation

### Scénario 1: Upgrade de opencv à retinaface

```timeline
Jour 1: Système utilise opencv
  - Insuree A vérifié → embedding stocké (opencv)
  - Insuree B vérifié → embedding stocké (opencv)

Jour 2: Admin change config vers retinaface
  - Insuree A vérifié → détection changement → recalcul auto → ✅
  - Insuree B vérifié → détection changement → recalcul auto → ✅

Jour 3+: Tous les embeddings sont à jour
  - Insuree A vérifié → fast path (retinaface) → ✅
  - Insuree B vérifié → fast path (retinaface) → ✅
```

### Scénario 2: Nouvel insuree

```timeline
Enrollment: Photo uploadée
  - Pas d'embedding calculé

Première vérification:
  - 🐢 Slow path (2-3s)
  - ✓ Vérification réussie
  - 💾 Embedding calculé et stocké automatiquement

Deuxième vérification:
  - ⚡ Fast path (200ms)
  - ✓ Utilise l'embedding stocké
```

### Scénario 3: Test avec différentes configurations

```timeline
Test 1: ArcFace + opencv
  - Vérification OK
  - Score: 45%

Admin change config: ArcFace + retinaface

Test 2: ArcFace + retinaface
  - ⚠ Détection: config a changé
  - 🔄 Recalcul automatique
  - ✓ Vérification OK
  - Score: 85% (meilleur!)
```

## Logs détaillés

Le système produit des logs explicites pour chaque action:

```log
# Config n'a pas changé (normal)
✓ Embedding config matches current config
⚡ Fast path: Using stored embedding

# Config a changé (recalcul auto)
⚠ Embedding configuration has changed!
   Stored config: {'detector_backend': 'opencv', ...}
   Current config: {'detector_backend': 'retinaface', ...}
🔄 Recalculating embedding with new configuration...
✓ Embedding recalculated successfully

# Première vérification (calcul auto)
🐢 Slow path: Full image-vs-image comparison
✓ Verification successful
💾 Verification successful - computing embedding for future fast path...
✓ Embedding stored - next verification will use fast path
```

## Avantages

✅ **Zéro intervention manuelle** - Tout est automatique
✅ **Toujours à jour** - Les embeddings restent compatibles
✅ **Performance optimale** - Fast path dès la 2ème vérification
✅ **Migration transparente** - Changement de config sans downtime
✅ **Audit trail complet** - Chaque embedding sait comment il a été calculé

## Migration depuis l'ancien système

Les embeddings existants (sans metadata) seront automatiquement détectés comme obsolètes et recalculés lors de la prochaine vérification.

Aucune action manuelle n'est requise.

## Configuration

Le système est contrôlé par:

```python
# apps.py
DEFAULT_CFG = {
    "store_embeddings": True,  # Active le système
    "provider_config": {
        "detector_backend": "retinaface",
        "enforce_detection": True,
    }
}
```

Tout changement dans `provider_config` sera automatiquement détecté et géré.

## Performances

| Scénario | Temps |
|----------|-------|
| Fast path (embedding valide) | ~200ms |
| Slow path (pas d'embedding) | ~2-3s |
| Slow path + calcul auto | ~3-5s (une seule fois) |
| Recalcul auto (config changée) | ~2-3s (une seule fois) |

Après la première vérification, toutes les suivantes utilisent le fast path (200ms).
