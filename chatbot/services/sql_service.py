import re
import json
from django.db import connection


class SQLService:
    """Service sécurisé pour interroger Microsoft SQL Server."""

    DANGEROUS_KEYWORDS = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'EXEC', 'EXECUTE', 'TRUNCATE', 'MERGE', 'GRANT', 'REVOKE',
        'DENY', 'BACKUP', 'RESTORE', 'XP_', 'SP_EXECUTESQL',
        'OPENROWSET', 'OPENDATASOURCE', 'BULK', 'SHUTDOWN',
    ]

    def get_schema(self):
        """Retourne le schéma complet depuis INFORMATION_SCHEMA."""
        schema = {}
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                cursor.execute("""
                    SELECT
                        COLUMN_NAME,
                        DATA_TYPE,
                        IS_NULLABLE,
                        CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                """, [table])
                columns = []
                for col in cursor.fetchall():
                    columns.append({
                        'name': col[0],
                        'type': col[1],
                        'nullable': col[2] == 'YES',
                        'max_length': col[3],
                    })
                schema[table] = columns

            # Relations FK
            cursor.execute("""
                SELECT
                    fk.TABLE_NAME AS from_table,
                    fk.COLUMN_NAME AS from_col,
                    pk.TABLE_NAME AS to_table,
                    pk.COLUMN_NAME AS to_col
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fk
                    ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk
                    ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
            """)
            relations = cursor.fetchall()

        return schema, relations

    def format_schema_for_prompt(self):
        """Formate le schéma de la base pour le prompt Mistral."""
        schema, relations = self.get_schema()

        lines = [
            "=== SCHÉMA Microsoft SQL Server (base: Projet_pfe) ===\n",
            "TABLES PRINCIPALES:",
            "- blog_customuser : utilisateurs (nom, prenom, filiale, email, role, is_active, is_staff)",
            "- reports_report : rapports PDF soumis (title, file, uploaded_at, user_id, status, processed_text, is_deleted)",
            "- reports_rapportheader : en-têtes des rapports d'essais (client, date_emission, ose, code, bon_de_commande, nature_echantillon, transport_par, date_prelevement, date_reception, date_debut_essais, responsable_laboratoire, is_deleted)",
            "- reports_rapportresultat : résultats des essais (header_id, essai, methode_essai, resultat, unite, is_deleted)",
            "",
            "STATUTS RAPPORT: PENDING, PROCESSING, COMPLETED, FAILED, REFUSED",
            "RÔLES UTILISATEUR: admin, user",
            "",
            "SCHÉMA DÉTAILLÉ:",
        ]

        for table_name, columns in schema.items():
            lines.append(f"\nTABLE: {table_name}")
            for col in columns:
                nullable = "NULL" if col['nullable'] else "NOT NULL"
                max_len = f"({col['max_length']})" if col['max_length'] else ""
                lines.append(f"  {col['name']}: {col['type']}{max_len} {nullable}")

        if relations:
            lines.append("\nRELATIONS (FK):")
            for rel in relations:
                lines.append(f"  {rel[0]}.{rel[1]} → {rel[2]}.{rel[3]}")

        lines.append("\nRÈGLES SQL:")
        lines.append("- Toujours filtrer: WHERE is_deleted = 0 (quand la colonne existe)")
        lines.append("- JOIN reports_rapportheader ON report_id = reports_report.id")
        lines.append("- JOIN reports_rapportresultat ON header_id = reports_rapportheader.id")

        return "\n".join(lines)

    def enforce_user_filter(self, query: str, user_id: int) -> str:
        """
        Filet de sécurité : injecte user_id dans la requête si Mistral l'a oublié.
        Uniquement pour les requêtes sur reports_report.
        """
        if 'reports_report' not in query.lower():
            return query

        # Déjà filtré ?
        if re.search(rf'user_id\s*=\s*{user_id}', query, re.IGNORECASE):
            return query

        # Trouver l'alias de reports_report (ex: "reports_report r" → alias "r")
        alias_match = re.search(
            r'\breports_report\b\s+(?:AS\s+)?([a-zA-Z_]\w*)\b',
            query, re.IGNORECASE
        )
        if alias_match:
            ref = alias_match.group(1)
            # Exclure les mots-clés SQL comme WHERE, ON, SET...
            if ref.upper() in ('WHERE', 'ON', 'SET', 'JOIN', 'AND', 'OR'):
                ref = 'reports_report'
        else:
            ref = 'reports_report'

        condition = f"{ref}.user_id = {user_id}"

        # Injecter dans le WHERE existant ou créer un WHERE
        where_match = re.search(r'\bWHERE\b', query, re.IGNORECASE)
        if where_match:
            pos = where_match.end()
            query = query[:pos] + f" {condition} AND " + query[pos:]
        else:
            order_match = re.search(r'\b(ORDER\s+BY|GROUP\s+BY|HAVING)\b', query, re.IGNORECASE)
            if order_match:
                pos = order_match.start()
                query = query[:pos] + f" WHERE {condition} " + query[pos:]
            else:
                query = query.rstrip('; ') + f" WHERE {condition}"

        return query

    def validate_query(self, query: str) -> tuple[bool, str]:
        """Valide que la requête est un SELECT sécurisé. Retourne (valide, raison)."""
        clean = query.strip()
        # Supprimer commentaires SQL
        clean = re.sub(r'--.*$', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        clean = clean.strip().upper()

        # Autoriser SELECT et WITH (CTE — Common Table Expressions)
        if not (clean.startswith('SELECT') or clean.startswith('WITH')):
            return False, "Seules les requêtes SELECT sont autorisées."

        # Un WITH doit contenir un SELECT
        if clean.startswith('WITH') and 'SELECT' not in clean:
            return False, "Requête CTE invalide (SELECT manquant)."

        for kw in self.DANGEROUS_KEYWORDS:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, clean):
                return False, f"Mot-clé interdit détecté: {kw}"

        # Bloquer les requêtes multiples de modification
        if re.search(r';\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)', clean):
            return False, "Requête multiple non autorisée."

        return True, ""

    def execute_query(self, query: str, max_rows: int = 150) -> dict:
        """Exécute une requête SELECT et retourne les résultats."""
        valid, reason = self.validate_query(query)
        if not valid:
            return {'success': False, 'error': reason, 'data': [], 'columns': []}

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                if not cursor.description:
                    return {'success': True, 'data': [], 'columns': [], 'row_count': 0}

                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchmany(max_rows)

                data = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if val is None:
                            row_dict[col] = None
                        elif hasattr(val, 'isoformat'):
                            row_dict[col] = val.isoformat()
                        elif isinstance(val, (int, float, bool)):
                            row_dict[col] = val
                        else:
                            row_dict[col] = str(val)
                    data.append(row_dict)

                return {
                    'success': True,
                    'columns': columns,
                    'data': data,
                    'row_count': len(data),
                    'truncated': len(data) == max_rows,
                }

        except Exception as e:
            return {'success': False, 'error': str(e), 'data': [], 'columns': []}

    def format_results_for_prompt(self, results: dict) -> str:
        """Formate les résultats SQL pour le prompt de génération de réponse."""
        if not results.get('success'):
            return f"ERREUR SQL: {results.get('error', 'Erreur inconnue')}"

        if not results.get('data'):
            return "La requête SQL n'a retourné aucun résultat (0 lignes)."

        lines = [f"RÉSULTATS SQL ({results['row_count']} lignes)"]
        if results.get('truncated'):
            lines.append("(Limité aux 150 premières lignes)")

        columns = results.get('columns', [])
        sep = " | "
        lines.append(sep.join(columns))
        lines.append("-" * 60)

        for row in results['data']:
            lines.append(sep.join(str(row.get(col, '')) for col in columns))

        return "\n".join(lines)
