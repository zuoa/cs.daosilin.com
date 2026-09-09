export const SITE_NAME = '熊掌CS Major'

export function nextDocumentTitle(route, currentTitle, isFirstNavigation = false) {
  if (isFirstNavigation) return currentTitle
  const title = route?.meta?.title
  return title ? `${title} · ${SITE_NAME}` : currentTitle
}

export function applyPageTitle(title) {
  if (!title) return
  document.title = title
  const ogTitle = document.querySelector('meta[property="og:title"]')
  if (ogTitle) ogTitle.setAttribute('content', title)
  const twitterTitle = document.querySelector('meta[name="twitter:title"]')
  if (twitterTitle) twitterTitle.setAttribute('content', title)
}
