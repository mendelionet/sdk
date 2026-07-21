import type { ListResponse } from "./types.js";

/**
 * Turn a cursor-paginated endpoint into an async iterator over items. `fetchPage` gets the next
 * cursor (undefined for the first page) and returns one page; iteration stops when `has_more` is
 * false. Callers can also just await one `fetchPage` if they want a single page.
 */
export async function* paginate<T>(
  fetchPage: (cursor: string | undefined) => Promise<ListResponse<T>>,
): AsyncGenerator<T, void, unknown> {
  let cursor: string | undefined;
  do {
    const page = await fetchPage(cursor);
    for (const item of page.data) yield item;
    cursor = page.has_more ? page.next_cursor ?? undefined : undefined;
  } while (cursor);
}
