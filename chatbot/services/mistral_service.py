"""
Service Mistral AI via REST API.
Gère le filtrage par rôle (user/admin) et des réponses métier sans jargon technique.
"""
import json
import requests
from django.conf import settings
from .sql_service import SQLService


MISTRAL_API_BASE = "https://api.mistral.ai/v1"


class MistralService:

    # ── Prompt SQL ────────────────────────────────────────────────────────────
    SQL_SYSTEM_PROMPT = """\
Tu es un expert SQL Server. Génère UNIQUEMENT une requête SQL SELECT valide.

{schema}

{user_filter}

RÈGLES ABSOLUES:
1. Génère UNIQUEMENT une requête SELECT — jamais INSERT, UPDATE, DELETE, DROP, etc.
2. Utilise les vrais noms de tables (reports_rapportheader, reports_rapportresultat, reports_report, blog_customuser)
3. Filtre TOUJOURS les suppressions: WHERE is_deleted = 0 (quand la colonne existe)
4. Réponds UNIQUEMENT avec la requête SQL pure — sans backticks, sans explication, sans commentaire
5. Si la question ne nécessite pas de SQL, réponds exactement: NO_SQL_NEEDED
6. NE JAMAIS ajouter de filtre de date si l'utilisateur n'a pas mentionné de période, mois ou date
7. Filtre de date UNIQUEMENT si la question contient: "ce mois", "cette année", "aujourd'hui", "en janvier", etc.
8. Limite les résultats avec TOP 50 si approprié\
"""

    # ── Prompt réponse métier ─────────────────────────────────────────────────
    ANSWER_SYSTEM_PROMPT = """\
Tu es LabAssistant, l'assistant du laboratoire de Poulina Group Holding.
Tu fournis des réponses claires et professionnelles destinées aux utilisateurs métier (non-techniciens).

RÈGLES ABSOLUES — RÉPONSE MÉTIER:
1. Réponds UNIQUEMENT en te basant sur les données réelles fournies
2. INTERDIT: mentionner SQL, requêtes, tables, colonnes, base de données, permissions, erreurs techniques
3. INTERDIT: suggérer des actions techniques ("vérifier les droits", "contacter l'admin", etc.)
4. INTERDIT: montrer du code ou des requêtes
5. INTERDIT: utiliser "période demandée", "pour cette période" si l'utilisateur n'a pas mentionné de période
6. Si aucune donnée: réponds "Aucun résultat trouvé." sans mentionner de période
7. Si l'utilisateur demande un total SANS préciser de période → répondre "au total" ou "en tout"
8. Utilise le markdown pour structurer (##, **, listes, tableaux)
9. Réponds comme un rapport métier professionnel: chiffres clairs, résumés concis
10. Réponds en français\
"""

    def __init__(self):
        self.api_key     = settings.MISTRAL_API_KEY
        self.model       = getattr(settings, 'MISTRAL_MODEL', 'mistral-large-latest')
        self.sql_service = SQLService()
        self._session    = requests.Session()
        self._session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type':  'application/json',
            'Accept':        'application/json',
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_history(self, history, limit=6):
        if not history:
            return []
        return [{'role': m['role'], 'content': m['content']} for m in history[-limit:]]

    def _chat(self, messages: list, temperature=0.3, max_tokens=2000) -> str:
        import time
        payload = {
            'model':       self.model,
            'messages':    messages,
            'temperature': temperature,
            'max_tokens':  max_tokens,
        }
        for attempt in range(3):
            r = self._session.post(
                f'{MISTRAL_API_BASE}/chat/completions',
                json=payload,
                timeout=90,
            )
            if r.status_code == 429:
                # Rate limit — attendre et réessayer
                wait = 5 * (attempt + 1)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
        raise Exception("Limite de requêtes Mistral atteinte. Attendez quelques secondes avant de réessayer.")

    def _user_filter_prompt(self, user) -> str:
        """Génère la contrainte SQL selon le rôle de l'utilisateur."""
        if user.role == 'admin':
            return (
                "ACCES ADMINISTRATEUR: Tu as acces a TOUTES les donnees de tous les utilisateurs.\n"
                "IMPORTANT: Quand l'admin dit 'mes rapports', 'mes essais', 'mes clients' etc., "
                "cela signifie TOUS les rapports/essais/clients de la base — PAS uniquement ceux d'un utilisateur specifique.\n"
                "Ne jamais filtrer par user_id pour un administrateur.\n"
                "Exemples corrects pour admin:\n"
                "• 'mes essais de pH' → SELECT rr.essai, rr.resultat, rh.client FROM reports_rapportresultat rr JOIN reports_rapportheader rh ON rh.id = rr.header_id WHERE rr.essai LIKE N'%pH%' AND rr.is_deleted = 0\n"
                "• 'mes rapports' → SELECT title, status, uploaded_at FROM reports_report WHERE is_deleted = 0 ORDER BY uploaded_at DESC\n"
                "• 'mes clients' → SELECT DISTINCT client FROM reports_rapportheader WHERE is_deleted = 0"
            )
        uid = user.pk
        return (
            f"UTILISATEUR: {user.nom} (filiale: {user.filiale}) — ID = {uid}\n\n"
            f"REGLE ABSOLUE: inclure TOUJOURS 'user_id = {uid}' dans chaque requete.\n\n"
            f"EXEMPLES EXACTS:\n"
            f"• Nombre total: SELECT COUNT(*) AS total FROM reports_report WHERE user_id = {uid} AND is_deleted = 0\n"
            f"• Liste rapports: SELECT title, status, uploaded_at FROM reports_report WHERE user_id = {uid} AND is_deleted = 0 ORDER BY uploaded_at DESC\n"
            f"• Par statut: SELECT status, COUNT(*) AS nb FROM reports_report WHERE user_id = {uid} AND is_deleted = 0 GROUP BY status\n"
            f"• Clients: SELECT DISTINCT rh.client FROM reports_rapportheader rh JOIN reports_report r ON r.id = rh.report_id WHERE r.user_id = {uid} AND r.is_deleted = 0\n"
            f"• Essais: SELECT rr.essai, rr.resultat, rr.unite FROM reports_rapportresultat rr JOIN reports_rapportheader rh ON rh.id = rr.header_id JOIN reports_report r ON r.id = rh.report_id WHERE r.user_id = {uid} AND r.is_deleted = 0\n\n"
            f"INTERDIT: requete sans user_id = {uid}."
        )

    # ── Méthodes publiques ────────────────────────────────────────────────────

    def _fallback_query(self, question: str, user) -> str:
        """
        Requête de secours simple quand la requête complexe échoue.
        Détecte le type de question et retourne une requête basique.
        """
        q = question.lower()
        uid_filter = f"WHERE user_id = {user.pk} AND is_deleted = 0" if user.role != 'admin' else "WHERE is_deleted = 0"

        if any(w in q for w in ['statistique', 'analyse', 'global', 'résumé', 'bilan']):
            return (
                f"SELECT status, COUNT(*) AS nombre "
                f"FROM reports_report {uid_filter} "
                f"GROUP BY status ORDER BY nombre DESC"
            )
        if any(w in q for w in ['client', 'clients']):
            if user.role == 'admin':
                return "SELECT DISTINCT rh.client, COUNT(*) AS nb FROM reports_rapportheader rh JOIN reports_report r ON r.id = rh.report_id WHERE r.is_deleted = 0 AND rh.is_deleted = 0 GROUP BY rh.client ORDER BY nb DESC"
            return (f"SELECT DISTINCT rh.client, COUNT(*) AS nb FROM reports_rapportheader rh "
                    f"JOIN reports_report r ON r.id = rh.report_id "
                    f"WHERE r.user_id = {user.pk} AND r.is_deleted = 0 AND rh.is_deleted = 0 "
                    f"GROUP BY rh.client ORDER BY nb DESC")
        if any(w in q for w in ['rapport', 'rapports', 'total', 'nombre']):
            return f"SELECT COUNT(*) AS total_rapports FROM reports_report {uid_filter}"
        return ""

    def generate_sql_query(self, question: str, schema: str, user, history=None) -> str:
        user_filter = self._user_filter_prompt(user)
        messages = [
            {'role': 'system', 'content': self.SQL_SYSTEM_PROMPT.format(
                schema=schema, user_filter=user_filter
            )},
            *self._build_history(history, 4),
            {'role': 'user', 'content': question},
        ]
        return self._chat(messages, temperature=0.05, max_tokens=600)

    def generate_answer(self, question: str, sql_results: str, user, history=None) -> str:
        role_label = "Administrateur" if user.role == 'admin' else f"Utilisateur ({user.filiale})"
        context = (
            f"Question posée par {role_label}: {question}\n\n"
            f"Données disponibles:\n{sql_results}"
        )
        messages = [
            {'role': 'system', 'content': self.ANSWER_SYSTEM_PROMPT},
            *self._build_history(history, 6),
            {'role': 'user', 'content': context},
        ]
        return self._chat(messages, temperature=0.3, max_tokens=2000)

    # ── Mots-clés et types de graphiques ─────────────────────────────────────
    CHART_KEYWORDS = [
        'graphique', 'graphe', 'graph', 'visuel', 'visualis', 'montre',
        'comparaison', 'compare', 'comparer', 'affiche', 'dessine', 'trace',
        'évolution', 'evolution', 'tendance', 'progression', 'courbe',
        'répartition', 'distribution', 'secteur', 'anneau', 'camembert',
        'chart', 'diagramme', 'histogramme', 'barre', 'barres', 'cascade',
        'radar', 'polaire', 'doughnut', 'donut',
    ]

    # Correspondance mots → types Chart.js
    CHART_TYPE_MAP = [
        (['courbe', 'ligne', 'line', 'evolution', 'évolution', 'tendance', 'progression'],
         'line'),
        (['camembert', 'secteur', 'pie', 'répartition', 'distribution'],
         'pie'),
        (['anneau', 'donut', 'doughnut'],
         'doughnut'),
        (['radar', 'araignée', 'toile'],
         'radar'),
        (['polaire', 'polar'],
         'polarArea'),
        (['barre horizontale'],
         'bar'),
    ]

    def _detect_chart_type(self, question: str) -> str:
        q = question.lower()
        for keywords, chart_type in self.CHART_TYPE_MAP:
            if any(kw in q for kw in keywords):
                return chart_type
        return 'bar'

    def _should_generate_chart(self, question: str, user, raw_results: dict) -> bool:
        if user.role != 'admin':
            return False
        if not raw_results.get('success') or not raw_results.get('data'):
            return False
        if raw_results.get('row_count', 0) < 1:
            return False
        q = question.lower()
        return any(kw in q for kw in self.CHART_KEYWORDS)

    def generate_chart_data(self, question: str, sql_results: str, raw_results: dict) -> dict:
        """Génère un objet Chart.js complet à partir des données SQL."""
        preferred_type = self._detect_chart_type(question)

        prompt = (
            f"Question: {question}\n\n"
            f"Données SQL:\n{sql_results[:2500]}\n\n"
            f"Génère UNIQUEMENT un JSON valide (sans backticks, sans markdown) pour Chart.js.\n"
            f"Type de graphique préféré: {preferred_type}\n\n"
            f"Format EXACT attendu:\n"
            f'{{"should_chart":true,"type":"{preferred_type}","title":"Titre clair",'
            f'"labels":["Label1","Label2","Label3"],'
            f'"datasets":[{{"label":"Nom série","data":[val1,val2,val3]}}]}}\n\n'
            f"RÈGLES:\n"
            f"- Les valeurs dans data doivent être des NOMBRES (pas de chaînes)\n"
            f"- labels et data doivent avoir la même longueur\n"
            f"- Pour pie/doughnut: 1 seul dataset\n"
            f"- Pour line/bar: plusieurs datasets possibles\n"
            f"- should_chart DOIT être true car l'utilisateur a explicitement demandé un graphique\n"
            f"- Utilise les vraies valeurs des données fournies"
        )

        try:
            result = self._chat(
                [{'role': 'user', 'content': prompt}],
                temperature=0.05,
                max_tokens=800
            )
            # Nettoyer la réponse
            result = re.sub(r'```json\s*|```\s*', '', result).strip()
            # Extraire le JSON si entouré d'autre texte
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                result = json_match.group(0)

            data = json.loads(result)

            # Validation et nettoyage
            if not data.get('labels') or not data.get('datasets'):
                return {'should_chart': False}

            # S'assurer que les valeurs sont bien des nombres
            for ds in data['datasets']:
                ds['data'] = [
                    float(v) if v is not None else 0
                    for v in ds.get('data', [])
                ]

            data['should_chart'] = True
            return data

        except Exception:
            # Fallback : générer un graphique simple depuis les données brutes
            return self._fallback_chart(raw_results, preferred_type, question)

    def _fallback_chart(self, raw_results: dict, chart_type: str, question: str) -> dict:
        """Génère un graphique basique directement depuis les données SQL sans Mistral."""
        if not raw_results.get('success') or not raw_results.get('data'):
            return {'should_chart': False}

        data = raw_results['data']
        columns = raw_results.get('columns', [])
        if len(columns) < 2:
            return {'should_chart': False}

        try:
            label_col  = columns[0]
            value_cols = [c for c in columns[1:] if c != label_col]

            labels   = [str(row.get(label_col, ''))[:30] for row in data[:20]]
            datasets = []
            for vc in value_cols[:3]:
                values = []
                for row in data[:20]:
                    try:
                        values.append(float(row.get(vc, 0) or 0))
                    except (ValueError, TypeError):
                        values.append(0)
                datasets.append({'label': vc, 'data': values})

            return {
                'should_chart': True,
                'type':         chart_type,
                'title':        question[:60],
                'labels':       labels,
                'datasets':     datasets,
            }
        except Exception:
            return {'should_chart': False}

    def process_question(self, question: str, user, history=None) -> dict:
        """Pipeline: question → SQL filtré → données → réponse métier + graphique optionnel."""
        try:
            schema  = self.sql_service.format_schema_for_prompt()
            sql_raw = self.generate_sql_query(question, schema, user, history)

            if sql_raw.upper().strip() == 'NO_SQL_NEEDED':
                sql_query   = ''
                sql_results = 'Aucune donnée SQL requise pour cette question.'
                raw_results = {}
            else:
                if user.role != 'admin':
                    sql_raw = self.sql_service.enforce_user_filter(sql_raw, user.pk)
                sql_query   = sql_raw
                raw_results = self.sql_service.execute_query(sql_query)

                if not raw_results.get('success'):
                    fallback_sql = self._fallback_query(question, user)
                    if fallback_sql:
                        fallback_results = self.sql_service.execute_query(fallback_sql)
                        if fallback_results.get('success'):
                            sql_query   = fallback_sql
                            raw_results = fallback_results
                            sql_results = self.sql_service.format_results_for_prompt(raw_results)
                        else:
                            sql_results = "Aucune donnée disponible pour cette demande."
                    else:
                        sql_results = "Aucune donnée disponible pour cette demande."
                else:
                    sql_results = self.sql_service.format_results_for_prompt(raw_results)

            answer = self.generate_answer(question, sql_results, user, history)

            # Graphique (admin uniquement, si demandé)
            # Délai pour éviter le rate limit Mistral après les 2 premiers appels
            chart_data = None
            if self._should_generate_chart(question, user, raw_results):
                import time as _time
                _time.sleep(2)
                chart_data = self.generate_chart_data(question, sql_results, raw_results)

            return {
                'success':    True,
                'answer':     answer,
                'sql_query':  sql_query,
                'chart_data': chart_data,
            }

        except Exception as e:
            msg = str(e)
            if any(x in msg for x in ['429', 'Too Many Requests', 'Limite de requêtes', 'rate limit']):
                friendly = "⏳ Limite de requêtes Mistral atteinte. Attendez 15–20 secondes puis réessayez."
            elif any(x in msg.lower() for x in ['timeout', 'timed out', 'read timeout']):
                friendly = "⌛ La réponse prend trop de temps. Réessayez dans un instant."
            elif any(x in msg for x in ['401', 'Unauthorized', '403', 'Forbidden']):
                friendly = "🔑 Clé API Mistral invalide. Vérifiez le fichier .env."
            elif any(x in msg for x in ['503', '502', '504', 'Service Unavailable']):
                friendly = "⚠️ Le service Mistral est temporairement indisponible. Réessayez dans quelques instants."
            elif any(x in msg.lower() for x in ['connection', 'network', 'unreachable']):
                friendly = "🌐 Erreur de connexion réseau. Vérifiez votre connexion internet."
            else:
                friendly = f"⚠️ Une erreur s'est produite. Réessayez dans quelques secondes."
            return {
                'success': False,
                'answer':  friendly,
                'sql_query': '',
            }
