"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useEffect, useState } from "react";
import { riderApi } from "@/lib/api/rider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
      }),
  );
  useEffect(
    () =>
      riderApi.subscribe(() => {
        void client.invalidateQueries({
          predicate: (query) =>
            query.queryKey[0] === "rider-ui" ||
            query.queryKey[0] === "ops-data",
        });
      }),
    [client],
  );
  return (
    <QueryClientProvider client={client}>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </QueryClientProvider>
  );
}
