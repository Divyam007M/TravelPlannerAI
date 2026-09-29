import { Children, isValidElement } from 'react'

function elements(node, type) {
  return Children.toArray(node).filter(child => isValidElement(child) && child.type === type)
}

function textContent(node) {
  return Children.toArray(node).map(child =>
    isValidElement(child) ? textContent(child.props.children) : typeof child === 'string' || typeof child === 'number' ? String(child) : ''
  ).join('')
}

export default function PlanTable({ children }) {
  const head = elements(children, 'thead')[0]
  const body = elements(children, 'tbody')[0]
  const headers = head ? elements(elements(head.props.children, 'tr')[0]?.props.children, 'th').map(cell => textContent(cell.props.children).trim()) : []
  const rows = body ? elements(body.props.children, 'tr').map(row => elements(row.props.children, 'td').map(cell => cell.props.children)) : []
  const isItinerary = headers.length > 1 && rows.length > 0 && (
    /^day(?:\s|$)/i.test(headers[0]) ||
    (/^(?:time|period|date)(?:\s|$)/i.test(headers[0]) && headers.slice(1).some(header => /activit|place|sight|transport|cost|plan/i.test(header)))
  )

  if (!isItinerary) return <div className="table-scroll" role="region" aria-label="Travel details table" tabIndex="0"><table>{children}</table></div>

  return <div className="itinerary-days" aria-label="Day-by-day itinerary">
    {rows.map((cells, index) => <section className="itinerary-day" key={index}>
      <h4>{cells[0] || `Day ${index + 1}`}</h4>
      <dl>{headers.slice(1).map((header, column) => <div className="itinerary-field" key={column}>
        <dt>{header || `Detail ${column + 1}`}</dt>
        <dd>{cells[column + 1] || '—'}</dd>
      </div>)}</dl>
    </section>)}
  </div>
}
