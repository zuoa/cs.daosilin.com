<script>
import { h } from 'vue'

const icons = {
  activity: [['path', { d: 'M3 12h4l2.5-7 5 14 2.5-7h4' }]],
  alert: [['circle', { cx: '12', cy: '12', r: '9' }], ['path', { d: 'M12 8v5' }], ['path', { d: 'M12 16h.01' }]],
  archive: [['rect', { x: '3', y: '5', width: '18', height: '4', rx: '1' }], ['path', { d: 'M5 9v10h14V9M10 13h4' }]],
  arrowLeft: [['path', { d: 'm15 18-6-6 6-6' }]],
  arrowRight: [['path', { d: 'm9 18 6-6-6-6' }]],
  arrowUp: [['path', { d: 'm6 15 6-6 6 6' }]],
  calendar: [['rect', { x: '3', y: '5', width: '18', height: '16', rx: '2' }], ['path', { d: 'M16 3v4M8 3v4M3 10h18' }]],
  check: [['path', { d: 'm5 12 4 4L19 6' }]],
  chevronDown: [['path', { d: 'm6 9 6 6 6-6' }]],
  chevronRight: [['path', { d: 'm9 18 6-6-6-6' }]],
  database: [['ellipse', { cx: '12', cy: '5', rx: '8', ry: '3' }], ['path', { d: 'M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5' }], ['path', { d: 'M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7' }]],
  copy: [['rect', { x: '8', y: '8', width: '12', height: '12', rx: '2' }], ['path', { d: 'M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2' }]],
  edit: [['path', { d: 'M12 20h9' }], ['path', { d: 'M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z' }]],
  external: [['path', { d: 'M14 4h6v6M20 4l-9 9' }], ['path', { d: 'M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6' }]],
  filter: [['path', { d: 'M4 6h16M7 12h10M10 18h4' }]],
  home: [['path', { d: 'm3 11 9-8 9 8' }], ['path', { d: 'M5 10v10h14V10M9 20v-6h6v6' }]],
  key: [['circle', { cx: '8', cy: '15', r: '4' }], ['path', { d: 'm11 12 8-8M15 8l3 3M17 6l2 2' }]],
  layers: [['path', { d: 'm12 2 9 5-9 5-9-5Z' }], ['path', { d: 'm3 12 9 5 9-5M3 17l9 5 9-5' }]],
  logout: [['path', { d: 'M10 17l5-5-5-5M15 12H3' }], ['path', { d: 'M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5' }]],
  plus: [['path', { d: 'M12 5v14M5 12h14' }]],
  refresh: [['path', { d: 'M20 11a8 8 0 1 0-2.3 5.7' }], ['path', { d: 'M20 4v7h-7' }]],
  save: [['path', { d: 'M5 3h12l2 2v16H5Z' }], ['path', { d: 'M8 3v6h8V3M8 21v-7h8v7' }]],
  search: [['circle', { cx: '11', cy: '11', r: '7' }], ['path', { d: 'm20 20-4-4' }]],
  shield: [['path', { d: 'M12 3 4 6v5c0 5 3.4 8.6 8 10 4.6-1.4 8-5 8-10V6Z' }], ['path', { d: 'm9 12 2 2 4-4' }]],
  target: [['circle', { cx: '12', cy: '12', r: '9' }], ['circle', { cx: '12', cy: '12', r: '4' }], ['path', { d: 'M12 1v4M12 19v4M1 12h4M19 12h4' }]],
  tierHam: [['path', { d: 'm12 3 1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9Z' }], ['path', { d: 'M19 3v3M20.5 4.5h-3M5 17v4M7 19H3' }]],
  tierElite: [['path', { d: 'm4 8 4 4 4-7 4 7 4-4-2 11H6Z' }], ['path', { d: 'M6 19h12' }]],
  tierUpper: [['circle', { cx: '8', cy: '8', r: '3' }], ['path', { d: 'M3 20v-1a5 5 0 0 1 10 0v1M16 11l3-3 3 3M19 8v11' }]],
  tierNpc: [['rect', { x: '4', y: '6', width: '16', height: '13', rx: '2' }], ['path', { d: 'M9 11h.01M15 11h.01M9 15h6M12 3v3' }]],
  tierBottom: [['path', { d: 'm4 6 6 6 4-4 6 6' }], ['path', { d: 'M20 9v5h-5M5 20h14' }]],
  trash: [['path', { d: 'M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6' }]],
  trophy: [['path', { d: 'M8 4h8v5a4 4 0 0 1-8 0Z' }], ['path', { d: 'M8 6H4v2a4 4 0 0 0 4 4M16 6h4v2a4 4 0 0 1-4 4M12 13v5M8 21h8M9 18h6' }]],
  userPlus: [['circle', { cx: '9', cy: '8', r: '4' }], ['path', { d: 'M3 21v-2a6 6 0 0 1 12 0v2M19 8v6M16 11h6' }]],
  users: [['circle', { cx: '9', cy: '8', r: '4' }], ['path', { d: 'M3 21v-2a6 6 0 0 1 12 0v2M16 4.5a4 4 0 0 1 0 7.5M17 15a6 6 0 0 1 4 6' }]],
  x: [['path', { d: 'm6 6 12 12M18 6 6 18' }]],
}

export default {
  props: {
    name: { type: String, required: true },
    size: { type: [Number, String], default: 18 },
  },
  setup(props) {
    return () => h('svg', {
      viewBox: '0 0 24 24',
      width: props.size,
      height: props.size,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 1.8,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'aria-hidden': 'true',
      focusable: 'false',
    }, (icons[props.name] || icons.activity).map(([tag, attrs]) => h(tag, attrs)))
  },
}
</script>
