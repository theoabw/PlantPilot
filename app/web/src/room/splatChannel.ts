/** A short name for the baked channel a filter URL loads, for the swap progress pill. */
export function channelLabel(url: string | null | undefined): string {
  if (!url) {
    return 'photo'
  }
  const name = url.split('?')[0].split('/').filter(Boolean).pop() ?? ''
  if (!url.includes('/api/filter/') || !name) {
    return 'photo'
  }
  if (name === 'edges_base') {
    return 'edges'
  }
  return name.replace(/_/g, ' ')
}
