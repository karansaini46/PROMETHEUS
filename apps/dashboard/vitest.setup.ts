import "@testing-library/jest-dom/vitest";

const storageMock: Record<string, string> = {};

const mockLocalStorage = {
  getItem: (key: string): string | null => (key in storageMock ? storageMock[key] : null),
  setItem: (key: string, value: string): void => {
    storageMock[key] = String(value);
  },
  removeItem: (key: string): void => {
    delete storageMock[key];
  },
  clear: (): void => {
    for (const key in storageMock) {
      delete storageMock[key];
    }
  },
  key: (i: number): string | null => Object.keys(storageMock)[i] || null,
  get length(): number {
    return Object.keys(storageMock).length;
  },
};

Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: true,
  configurable: true,
});

if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", {
    value: mockLocalStorage,
    writable: true,
    configurable: true,
  });
}
