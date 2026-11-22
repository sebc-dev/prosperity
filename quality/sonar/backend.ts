import type { Failure } from './sonar-kit.ts';

/** Où tourne le scanner et d'où l'on interroge le serveur : le poste (mode local) ou la machine Sonar (mode SSH). */
export interface Backend {
  /** Lignes imprimées par `--dry-run` : aucune valeur secrète, aucun accès réseau. */
  describe: () => string[];
  /** Vérifie ce qui peut l'être avant les rapports (long) : fichier d'environnement, moteur de conteneur. */
  preflight: () => Promise<Failure | undefined>;
  /** Envoie les sources et les rapports, lance le scanner. */
  scan: () => Promise<Failure | undefined>;
  serverVersion: () => Promise<string | undefined>;
  readReportTask: () => Promise<string | undefined>;
  fetchTask: (taskId: string) => Promise<unknown>;
  dashboard: () => string;
  cleanup: () => Promise<void>;
}

/** Fin de sortie d'un outil, jeton masqué : de quoi diagnostiquer sans rien divulguer. */
export function tail(text: string, secrets: readonly string[] = []): string {
  const masked = secrets
    .filter((secret) => secret !== '')
    .reduce((line, secret) => line.split(secret).join('***'), text.trim());
  return masked.slice(-800);
}
