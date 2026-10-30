import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import createClient from "openapi-fetch";

import type { components } from "./schema";

export type Job = components["schemas"]["ResearchJobResponse"];
export type JobDetail = components["schemas"]["ResearchJobDetailResponse"];
export type JobStatus = Job["status"];
export type Stage = NonNullable<Job["current_stage"]>;
export type Report = components["schemas"]["ReportResponse"];
export type Claim = components["schemas"]["ClaimOut"];
export type Metric = components["schemas"]["MetricOut"];
export type Evidence = components["schemas"]["EvidenceOut"];
export type Filing = components["schemas"]["FilingOut"];
export type FinancialPeriod = components["schemas"]["FinancialPeriodOut"];
export type CompanySummary = components["schemas"]["CompanySummary"];
export type CompanyDetail = components["schemas"]["CompanyDetail"];
export type Meta = components["schemas"]["MetaResponse"];
export type CreateRequest = components["schemas"]["ResearchCreateRequest"];

export const api = createClient<import("./schema").paths>({ baseUrl: "" });

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function detail(error: unknown, status: number): ApiError {
  const body = error as { detail?: unknown } | undefined;
  if (typeof body?.detail === "string") return new ApiError(body.detail, status);
  if (Array.isArray(body?.detail)) {
    const first = body.detail[0] as { msg?: string; loc?: string[] } | undefined;
    const field = first?.loc?.at(-1);
    return new ApiError(field ? `${field}: ${first?.msg ?? "invalid"}` : (first?.msg ?? "Invalid request"), status);
  }
  return new ApiError(status ? `Request failed (${status})` : "The API is unreachable. Is the backend running?", status);
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result;
  try {
    result = await promise;
  } catch {
    throw new ApiError("The API is unreachable. Is the backend running on port 8000?", 0);
  }
  if (result.error !== undefined || result.data === undefined) throw detail(result.error, result.response.status);
  return result.data;
}

export const ACTIVE: JobStatus[] = ["queued", "running"];
export const isActive = (status: JobStatus) => ACTIVE.includes(status);

export function useJobs(params: { status?: JobStatus; ticker?: string; limit?: number } = {}) {
  return useInfiniteQuery({
    queryKey: ["jobs", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/research", {
          params: { query: { limit: params.limit ?? 20, cursor: pageParam, status: params.status, ticker: params.ticker || undefined } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) => page.items.some((job) => isActive(job.status))) ? 2000 : 15000,
  });
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => unwrap(api.GET("/api/v1/research/{job_id}", { params: { path: { job_id: jobId } } })),
    refetchInterval: (query) => (query.state.data && !isActive(query.state.data.status) ? false : 1500),
  });
}

export function useReport(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ["report", jobId],
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/research/{job_id}/report", { params: { path: { job_id: jobId } } })),
    staleTime: Infinity,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
}

export function useCompanies() {
  return useQuery({ queryKey: ["companies"], queryFn: () => unwrap(api.GET("/api/v1/companies")) });
}

export function useCompany(ticker: string) {
  return useQuery({
    queryKey: ["company", ticker],
    queryFn: () => unwrap(api.GET("/api/v1/companies/{ticker}", { params: { path: { ticker } } })),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
    refetchInterval: (query) =>
      query.state.data?.jobs.some((j) => isActive(j.status)) ? 3000 : false,
  });
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => unwrap(api.GET("/api/v1/meta")), refetchInterval: 10000 });
}

export function useSubmitResearch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ body, idempotencyKey }: { body: CreateRequest; idempotencyKey: string }) =>
      unwrap(api.POST("/api/v1/research", { body, params: { header: { "idempotency-key": idempotencyKey } } })),
    onSuccess: (job) => {
      client.setQueryData(["job", job.id], { ...job, stages: [] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["meta"] });
    },
  });
}

export function useJobAction(action: "cancel" | "retry") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      unwrap(
        action === "cancel"
          ? api.POST("/api/v1/research/{job_id}/cancel", { params: { path: { job_id: jobId } } })
          : api.POST("/api/v1/research/{job_id}/retry", { params: { path: { job_id: jobId } } }),
      ),
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["job", job.id] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
