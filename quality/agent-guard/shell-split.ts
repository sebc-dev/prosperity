/**
 * Découpe grossière d'une ligne de commande shell : segments (séparés par `;`, `&`,
 * `|`, retour à la ligne, parenthèses et accents graves), mots débarrassés de leurs
 * guillemets, et cibles de redirection d'écriture. Ce n'est pas un interpréteur : le
 * garde n'est pas exhaustif par décision (D-04), la CI reste le juge.
 */
export interface Segment {
  words: string[];
  writes: string[];
}

type Mode = 'word' | 'write' | 'discard';

const SEPARATORS = new Set([';', '&', '|', '\n', '(', ')', '`']);
const ESCAPABLE_IN_DOUBLE = new Set(['"', '\\', '$', '`']);
const REDIRECT_CHARS = new Set(['<', '>', '&', '|']);

class Splitter {
  private readonly segments: Segment[] = [];
  private words: string[] = [];
  private writes: string[] = [];
  private word = '';
  private inWord = false;
  private mode: Mode = 'word';

  run(command: string): Segment[] {
    let index = 0;
    while (index < command.length) {
      index = this.step(command, index) + 1;
    }
    this.endSegment();
    return this.segments;
  }

  private append(text: string): void {
    this.word += text;
    this.inWord = true;
  }

  private flush(): void {
    if (!this.inWord) {
      return;
    }
    if (this.mode === 'word') {
      this.words.push(this.word);
    } else if (this.mode === 'write') {
      this.writes.push(this.word);
    }
    this.word = '';
    this.inWord = false;
    this.mode = 'word';
  }

  private endSegment(): void {
    this.flush();
    if (this.words.length > 0 || this.writes.length > 0) {
      this.segments.push({ words: this.words, writes: this.writes });
    }
    this.words = [];
    this.writes = [];
    this.mode = 'word';
  }

  /** Traite le caractère à `index` ; renvoie l'indice du dernier caractère consommé. */
  private step(command: string, index: number): number {
    const char = command.charAt(index);
    const consumed = this.special(command, index, char);
    if (consumed !== undefined) {
      return consumed;
    }
    if (SEPARATORS.has(char)) {
      this.endSegment();
    } else if (char === ' ' || char === '\t') {
      this.flush();
    } else {
      this.append(char);
    }
    return index;
  }

  /** Guillemets, échappement, commentaire et redirection ; `undefined` pour un caractère ordinaire. */
  private special(command: string, index: number, char: string): number | undefined {
    if (char === "'") {
      return this.singleQuoted(command, index);
    }
    if (char === '"') {
      return this.doubleQuoted(command, index);
    }
    if (char === '\\') {
      return this.escaped(command, index);
    }
    if (char === '#' && !this.inWord) {
      const eol = command.indexOf('\n', index);
      return eol === -1 ? command.length : eol - 1;
    }
    const isRedirect =
      char === '>' || char === '<' || (char === '&' && command.charAt(index + 1) === '>');
    return isRedirect ? this.redirect(command, index) : undefined;
  }

  private singleQuoted(command: string, index: number): number {
    const end = command.indexOf("'", index + 1);
    this.append(command.slice(index + 1, end === -1 ? command.length : end));
    return end === -1 ? command.length : end;
  }

  private doubleQuoted(command: string, index: number): number {
    this.append('');
    let position = index + 1;
    while (position < command.length && command.charAt(position) !== '"') {
      const char = command.charAt(position);
      const next = command.charAt(position + 1);
      if (char === '\\' && ESCAPABLE_IN_DOUBLE.has(next)) {
        this.append(next);
        position += 1;
      } else {
        this.append(char);
      }
      position += 1;
    }
    return position;
  }

  private escaped(command: string, index: number): number {
    const next = command.charAt(index + 1);
    if (next === '') {
      return index;
    }
    if (next !== '\n') {
      this.append(next);
    }
    return index + 1;
  }

  private redirect(command: string, index: number): number {
    if (this.inWord && /^\d+$/.test(this.word)) {
      // Descripteur de fichier (`2>`) : ce n'est pas un argument.
      this.word = '';
      this.inWord = false;
    } else {
      this.flush();
    }
    let end = index;
    while (end < command.length && REDIRECT_CHARS.has(command.charAt(end))) {
      end += 1;
    }
    this.mode = command.charAt(index) === '<' ? 'discard' : 'write';
    return end - 1;
  }
}

export function splitCommand(command: string): Segment[] {
  return new Splitter().run(command);
}
