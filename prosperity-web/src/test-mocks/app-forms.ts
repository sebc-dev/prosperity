/* eslint-disable @typescript-eslint/no-unused-vars */
export function enhance(form: HTMLFormElement) {
	return { destroy() {} };
}
export function deserialize(result: unknown) {
	return result;
}
export function applyAction(result: unknown) {
	return Promise.resolve();
}
