export const page = { subscribe() {} };
export const navigating = { subscribe() {} };
export const updated = {
	subscribe() {},
	check() {
		return Promise.resolve(false);
	}
};
