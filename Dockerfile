# ──────────────────────────────────────────────────────────────────────────
# Image du microservice IA de recrutement (FastAPI + Mistral + pyodbc).
# Base légère Python 3.11 ; on installe juste ce qu'il faut pour faire tourner
# le service (pas les libs ML de recherche).
# ──────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Sorties non bufferisées (logs visibles en direct) + pas de .pyc.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Dépendances système pour compiler et importer pyodbc.
# gcc/g++/unixodbc-dev suffisent à installer pyodbc et à lancer le service.
#
# NB : le driver "msodbcsql17" (connexion live à SQL Server) n'est PAS installé ici.
# En CI/conteneur le service ne se connecte pas à la base locale ; pour un déploiement
# réel avec accès SQL Server, ajouter le dépôt Microsoft correspondant à l'OS cible
# (ex: packages.microsoft.com/config/debian/12) puis `ACCEPT_EULA=Y apt-get install msodbcsql18`.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ unixodbc-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) On copie d'abord les dépendances seules : tant qu'elles ne changent pas,
#    Docker réutilise cette couche en cache (build plus rapide).
COPY requirements-runtime.txt .
RUN pip install --upgrade pip && pip install -r requirements-runtime.txt

# 2) Puis le code applicatif.
COPY ai_service ./ai_service

# Le service écoute sur le port 8000 (uvicorn).
EXPOSE 8000

# Lancement du serveur. (Le cron de fond démarre via le lifespan de FastAPI.)
CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
