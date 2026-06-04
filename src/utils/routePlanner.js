import * as turf from '@turf/turf'

export function planRoute(points, days, center) {
  if (points.length === 0) return []
  if (days <= 0) days = 1
  if (days > points.length) days = points.length

  const validPoints = points.filter(p => p.geo && p.geo.length === 2)
  if (validPoints.length === 0) return []

  if (days === 1) {
    const sorted = nearestNeighborSort(validPoints, center)
    const totalDistance = calculateTotalDistance(sorted)
    return [{
      day: 1,
      points: sorted,
      distance: totalDistance,
      pointCount: sorted.length
    }]
  }

  const features = validPoints.map(p => turf.point([p.geo[1], p.geo[0]], { id: p.id }))
  const collection = turf.featureCollection(features)

  let clusters
  try {
    clusters = turf.clustersKmeans(collection, { numberOfClusters: days })
  } catch (e) {
    const sorted = nearestNeighborSort(validPoints, center)
    const totalDistance = calculateTotalDistance(sorted)
    return [{
      day: 1,
      points: sorted,
      distance: totalDistance,
      pointCount: sorted.length
    }]
  }

  const clusterGroups = {}
  clusters.features.forEach(f => {
    const cluster = f.properties.cluster
    if (!clusterGroups[cluster]) {
      clusterGroups[cluster] = []
    }
    const pointId = f.properties.id
    const originalPoint = validPoints.find(p => p.id === pointId)
    if (originalPoint) {
      clusterGroups[cluster].push(originalPoint)
    }
  })

  const clusterEntries = Object.entries(clusterGroups).sort((a, b) => {
    const centerA = calculateClusterCenter(a[1])
    const centerB = calculateClusterCenter(b[1])
    const distA = turf.distance(
      turf.point([center[1], center[0]]),
      turf.point([centerA[1], centerA[0]])
    )
    const distB = turf.distance(
      turf.point([center[1], center[0]]),
      turf.point([centerB[1], centerB[0]])
    )
    return distA - distB
  })

  const result = clusterEntries.map(([_, clusterPoints], index) => {
    const sortedPoints = nearestNeighborSort(clusterPoints, center)
    const totalDistance = calculateTotalDistance(sortedPoints)
    return {
      day: index + 1,
      points: sortedPoints,
      distance: totalDistance,
      pointCount: sortedPoints.length
    }
  })

  return result
}

function nearestNeighborSort(points, startPoint) {
  if (points.length <= 1) return [...points]

  const sorted = []
  const remaining = [...points]
  
  let nearestIdx = 0
  let minDist = Infinity
  remaining.forEach((p, idx) => {
    const dist = turf.distance(
      turf.point([startPoint[1], startPoint[0]]),
      turf.point([p.geo[1], p.geo[0]])
    )
    if (dist < minDist) {
      minDist = dist
      nearestIdx = idx
    }
  })
  
  sorted.push(remaining.splice(nearestIdx, 1)[0])

  while (remaining.length > 0) {
    const current = sorted[sorted.length - 1]
    let nearestIdx = 0
    let minDist = Infinity
    
    remaining.forEach((p, idx) => {
      const dist = turf.distance(
        turf.point([current.geo[1], current.geo[0]]),
        turf.point([p.geo[1], p.geo[0]])
      )
      if (dist < minDist) {
        minDist = dist
        nearestIdx = idx
      }
    })
    
    sorted.push(remaining.splice(nearestIdx, 1)[0])
  }

  return sorted
}

function calculateClusterCenter(points) {
  const lats = points.map(p => p.geo[0])
  const lngs = points.map(p => p.geo[1])
  return [
    lats.reduce((a, b) => a + b, 0) / lats.length,
    lngs.reduce((a, b) => a + b, 0) / lngs.length
  ]
}

function calculateTotalDistance(points) {
  if (points.length < 2) return 0
  
  let total = 0
  for (let i = 0; i < points.length - 1; i++) {
    const from = turf.point([points[i].geo[1], points[i].geo[0]])
    const to = turf.point([points[i + 1].geo[1], points[i + 1].geo[0]])
    total += turf.distance(from, to)
  }
  
  return Math.round(total * 100) / 100
}
