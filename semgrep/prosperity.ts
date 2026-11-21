declare function defineTool(name: string, config: object, handler: unknown): void;
declare const server: { registerTool(...args: unknown[]): void };
declare const db: { query(text: string): void };
declare const sql: { raw(text: string): void };
declare const req: { token: string; secret: string; signature: string };
declare const userInput: string;
declare const expected: string;
interface Principal {
  memberId: string;
}

// ruleid: prosperity.tool-handler-without-principal
defineTool('a', {}, async (input: string) => {
  return input;
});
// ruleid: prosperity.tool-handler-without-principal
defineTool('b', {}, async () => {
  return 1;
});
// ok: prosperity.tool-handler-without-principal
defineTool('c', {}, async (principal: Principal, input: string) => {
  return `${principal.memberId}${input}`;
});

// ruleid: prosperity.raw-registertool
server.registerTool('x', {}, () => 1);

// ruleid: prosperity.sql-concatenation
sql.raw('select * from t where id = ' + userInput);
// ruleid: prosperity.sql-concatenation
db.query(`select * from t where id = ${userInput}`);
// ok: prosperity.sql-concatenation
db.query('select * from t where id = $1');

// ruleid: prosperity.insecure-random-token
const weak = Math.random().toString(36);
// ok: prosperity.insecure-random-token
const strong = crypto.randomUUID();

// ruleid: prosperity.non-constant-time-secret-compare
const same = req.token === expected;
// ok: prosperity.non-constant-time-secret-compare
const same2 = req.token.length === expected.length;
