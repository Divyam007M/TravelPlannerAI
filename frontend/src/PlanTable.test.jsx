import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import PlanTable from './PlanTable'

function render(markdown) {
  return renderToStaticMarkup(<ReactMarkdown remarkPlugins={[remarkGfm]} components={{ table: PlanTable }} skipHtml>{markdown}</ReactMarkdown>)
}

describe('plan table display', () => {
  it('turns a five-day Bhopal table into labelled day sections without losing transport or cost', () => {
    const rows = Array.from({ length: 5 }, (_, index) =>
      `| Day ${index + 1} | Visit Upper Lake and a heritage site with a long walking route | Shared auto-rickshaw and local bus | ₹1,250–₹2,000 |`).join('\n')
    const html = render(`| Day | Activities | Transport | Day-wise Cost |\n| --- | --- | --- | --- |\n${rows}`)
    expect(html.match(/class="itinerary-day"/g)).toHaveLength(5)
    expect(html).toContain('Day-wise Cost')
    expect(html).toContain('₹1,250–₹2,000')
    expect(html).toContain('Shared auto-rickshaw and local bus')
    expect(html).not.toContain('<table')
  })

  it('handles an international plan with long names, missing cells and safe Markdown', () => {
    const html = render('| Day | Places and activities | Transport | Estimated local cost |\n| --- | --- | --- | --- |\n| Day 1 | São Bento railway station, Porto, Portugal, and a long waterfront walk | Metro, then regional train | €120–€180 |\n| Day 2 | [Museum](https://example.com) |  | |\n<script>alert(1)</script>')
    expect(html).toContain('São Bento railway station')
    expect(html).toContain('€120–€180')
    expect(html).toContain('Day 2')
    expect(html).toContain('—')
    expect(html).not.toContain('<script')
  })

  it('keeps ordinary data tables in a bounded scroll region', () => {
    const html = render('| Currency | Amount |\n| --- | --- |\n| INR | ₹10,000 |')
    expect(html).toContain('class="table-scroll"')
    expect(html).toContain('<table>')
  })
})
