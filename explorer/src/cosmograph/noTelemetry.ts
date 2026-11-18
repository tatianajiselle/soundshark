const nothing = Promise.resolve({ data: null, error: null });

export function createClient() {
  return {
    from: () => ({ insert: () => nothing }),
    rpc: () => nothing,
  };
}
