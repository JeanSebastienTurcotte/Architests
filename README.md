# Architest

Cet outil génère des versions aléatoires de tests en format LaTeX à partir d'une banque de questions. Cela inclut les fonctionnalités suivantes:

- paramètres aléatoires (via Sage)
- Création de graphique automatique (via Sage)
- Plusieurs versions différentes avec les mêmes questions
- Graine aléatoire (seed) retraçable pour recréer une version spécifique
- Une gestion en cache des paramètres et figures pour modifier le texte de la question sans tout refaire.

---

## Utilisation

Dans le dossier 'questions', créer les questions souhaitées. Un exemple de questions est disponible dans le fichier.

Dans le fichier 'config.yaml', configurer un ou des tests. Des exemples sont présents dans le fichier 'config_ex.yaml'. 
Dans l'invite de commande, taper:

```
python builder.py [options]
```

### Options disponibles

- `--questions nom`  
  Sélection spécifique de questions à utiliser. Le `nom` doit être présent dans le fichier `config.yaml`
- `--versions N`  
  Nombre de versions à générer. Comportement par défaut: `1`.

- `--solutions`  (Non testé encore)
  Inclure les solutions dans le rendu.

- `--answers`  (Non testé encore)
  Inclure les réponses dans le rendu.

- `--shuffle`  
  Mélanger l'ordre des questions dans les différentes versions. Les mêmes questions sont dans toutes les versions (avec des paramètres aléatoires potentiellement différents), mais pas dans le même ordre.

- `--seed N`  
  Outrepasse la génération aléatoire pour utiliser une graine spécifique. Utile pour reproduire une version lors du processus de création des questions.

- `--usecache`  
  Réutilise, si possible, les paramètres et figures de la dernière compilation.  
  - Lorsque l'argument est passé, les paramètres sont pris dans le fichier `cache/seeds_cache.yaml`.  
  - Les figures présentes dans le dossier `figures/` ne sont pas regénérées.  
  - Si un cache n'existe pas pour une version, les paramètres ou figures seront créés et ajoutés au cache pour le future.  

- `--debug`  
  Utile pour vérifier et comprendre des bugs qui pourraient survenir dans la génération aléatoire des paramàtres ou des figures.

---

## Comment fonctionne le versionnage aléatoire

- Par défaut, une nouvelle graine aléatoire globale est générée chaque fois que le programme est exécuté et est inscrite dans `config.yaml`.  
- De cette manière, chaque exécution a le potentiel d'être différente des précédentes.  
- Chaque question possède ensuite une graine aléatoire locale, composée de la somme de la graine aléatoire globale, du numéro de la version du test et de la fonction `hash` de l'identifiant et du sous-identifiant de la question. Ceci permet de s'assurer que de question en question, pour une même version, les paramètres aléatoires seront différents.
- Si `--seed` est présent, cette valeur prend priorité sur la valeur qui a été générée.  
- Si `--usecache` est présent, on utilise :
  - La **dernière graine globale** présente dans le fichier `config.yaml`  
  - Les paramètres générés précédemment se trouvant dans le fichier `cache/seeds_cache.yaml`.  
  - Les figures générées précédemment se trouvant dans le fichier `figures/`.

---

## Rendus

- Les tests sont générés en LaTeX dans le dossier `output/` sous la forme:  
  
  ``
  output/quiz_v1.tex  
  output/quiz_v2.tex  
  ...  
  ``
- Le fichier LaTeX est construit selon l'un des gabarits dans `templates/`. Par défaut, le gabarit `default.tex` est utilisé. (Le support pour plusieurs gabarit n'est pas encore là). 

---

## Exemples d'utilisation

Générer 3 versions du test appelé `test1` en mélangeant l'ordre des question:

```
python builder.py --questions test1 --versions 3 --shuffle
```

Corriger une erreur dans le texte d'une question et  **réutiliser les valeurs en cache**:

```
python builder.py --questions test1 --usecache --shuffle
```

Regénérer la version de `test2` avec la graine globale `42`.

```
python builder.py --questions test2 --versions 2 --seed 42
```

---

## Structure de dossier

```
.
├── builder.py
├── config.yaml
├── templates/
│   └── default.tex
├── questions/
│   ├── q1.yaml
│   ├── q2.yaml
│   └── ...
├── figures/
│   ├── q1_v1.png
│   ├── q1_v2.png
│  ├── ...
├── cache/
│   └── seeds_cache.yaml
└── output/
    ├── quiz_v1.tex
    ├── quiz_v2.tex
    ├── ...
```

## Construction de la banque de questions

Les fichiers de questions doivent être nommés "id".yaml où "id" est un identifiant aussi présent dans le fichier.

### Types de questions

Différents types de questions sont possibles.

#### Ouvertes

Pour les questions à démarche, à réponse textuelle ou autre.

#### Vrai ou faux

Pour ces questions, on peut formuler une question vrai ou faux et donner la réponse. Il est aussi possible de formuler une "même" question dans sa version "vraie" et "fausse". Une fonction choisira au hasard l'une des deux versions. Par exemple "un plus un égal deux" et "un plus un n'est pas égal à deux". La structure est la suivante: 

```
generate_params: |
      load("helpers/tf_randomizer.sage") 
      true_text = "Texte dont la réponse est vraie."
      false_text = "Texte dont la réponse est fausse."
      statement, answer = tf_randomizer(true_text, false_text)
    question: "{{ statement }}"
    answer: "{{ answer }}"
```

#### Choix multiples

