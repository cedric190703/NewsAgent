export type SourceType = "web" | "rss" | "knowledge_base";
export type OutputFormat = "briefing" | "newsletter" | "analysis" | "source_list";

export interface NewsQueryRequest {
  topic: string;
  section?: string;
  output_format: OutputFormat;
  sources: SourceType[];
  depth: number;
  include_citations: boolean;
}

export interface NewsSource {
  title: string;
  url?: string | null;
  source_type: SourceType;
  publisher?: string | null;
  published_at?: string | null;
  relevance_score: number;
  summary?: string | null;
}

export interface NewsQueryResponse {
  result_id: string;
  topic: string;
  generated_at: string;
  output_format: OutputFormat;
  executive_summary: string;
  key_points: string[];
  analysis: string;
  sources: NewsSource[];
  confidence: string;
  suggested_followups: string[];
  critic_notes: string[];
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function queryNews(payload: NewsQueryRequest): Promise<NewsQueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/news/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "The news request failed.");
  }

  return response.json();
}
