import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import { fetchChartTimeline } from "../api/clinical";
import { ApiError } from "../api/errors";
import type { TimelineItemDTO } from "../api/generated/iam-shell";
import { clinicalKeys } from "../api/queryClient";
import { isAbortError, mergeAbortSignals } from "../tenant/generation";
import { clinicalChartCoordinator } from "./clinicalChartCoordinator";
import { clinicalQueryPolicy } from "./queryPolicy";
import {
  SectionEmptyState,
  SectionErrorState,
  SectionLoadingState,
} from "./sectionStates";

function itemKey(item: TimelineItemDTO): string {
  return `${item.source_type}:${item.source_id}`;
}

export function TimelineView({
  organizationId,
  facilityId,
  patientIdentityId,
  generation,
  signal,
}: {
  organizationId: string;
  facilityId: string | null;
  patientIdentityId: string;
  generation: number;
  signal: AbortSignal;
}) {
  const { t } = useTranslation();
  const loadMoreLock = useRef(false);
  const query = useInfiniteQuery({
    queryKey: clinicalKeys.timeline(organizationId, patientIdentityId),
    queryFn: ({ pageParam, signal: querySignal }) => {
      if (!clinicalChartCoordinator.isCurrent(generation)) {
        throw new DOMException("Aborted", "AbortError");
      }
      return fetchChartTimeline({
        organizationId,
        facilityId,
        patientIdentityId,
        cursor: pageParam,
        signal: mergeAbortSignals(querySignal, signal),
      });
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more && lastPage.next_cursor ? lastPage.next_cursor : undefined,
    ...clinicalQueryPolicy,
  });

  const items = useMemo(() => {
    const seen = new Set<string>();
    const merged: TimelineItemDTO[] = [];
    for (const page of query.data?.pages ?? []) {
      for (const item of page.items) {
        const key = itemKey(item);
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        merged.push(item);
      }
    }
    return merged;
  }, [query.data]);

  const cursorError = query.error instanceof ApiError && query.error.status === 422;
  const loadMore = () => {
    if (
      loadMoreLock.current ||
      query.isFetchingNextPage ||
      cursorError ||
      !query.hasNextPage
    ) {
      return;
    }
    loadMoreLock.current = true;
    void query.fetchNextPage().finally(() => {
      loadMoreLock.current = false;
    });
  };

  if (query.isPending && items.length === 0) {
    return <SectionLoadingState />;
  }
  if (query.error && !cursorError) {
    if (isAbortError(query.error)) {
      return <SectionLoadingState />;
    }
    return <SectionErrorState onRetry={() => void query.refetch()} />;
  }
  if (items.length === 0 && !cursorError) {
    return <SectionEmptyState messageKey="chart.timelineEmpty" />;
  }

  return (
    <div className="chart-timeline">
      <h2>{t("chart.timeline")}</h2>
      <ol className="chart-timeline-list">
        {items.map((item) => (
          <li key={itemKey(item)} className="chart-timeline-item">
            <time dateTime={item.occurred_at}>{item.occurred_at}</time>
            <span>{item.source_type}</span>
            {item.code_display || item.code ? <span>{item.code_display || item.code}</span> : null}
            {item.status ? <span>{item.status}</span> : null}
          </li>
        ))}
      </ol>
      {cursorError ? (
        <div className="notice" role="alert">
          <p>{t("chart.cursorError")}</p>
        </div>
      ) : null}
      {query.hasNextPage && !cursorError ? (
        <button
          type="button"
          className="button"
          onClick={loadMore}
          disabled={query.isFetchingNextPage}
        >
          {t("chart.loadMore")}
        </button>
      ) : null}
    </div>
  );
}
