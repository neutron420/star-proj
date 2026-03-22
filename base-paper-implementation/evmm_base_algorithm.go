package evmm

import (
	"math"
	"sort"
	"sync"
	"time"
)

const (
	QuotaPause       = 20
	ThrScaleUp       = 0.80
	ThrScaleDown     = 0.70
	ThrCheckpoint    = 0.82
	ThrReCheckpoint  = 120
	ThrContainerStop = 0.95
	Tmax             = 60
	BinSize          = 10
	MinTimeWindow    = 10
	MUtilTarget      = 0.75
)

type Container struct {
	ID            string
	Timestamp     int64
	MemLimit      int64
	MemUsedHist   []int64
	CPUCoresHist  []float64
	ScaleUpCount  int
	PauseTime     float64
	ExecutionTime float64
	IsPaused      bool
	IsCheckpoint  bool
	LastCheckTime time.Time
	ScaleUpSize   int64
	PriorityScore float64
}

type Node struct {
	ID            string
	MemSize       int64
	MemUsage      int64
	CPUCores      float64
	TotalScaleUps int
}

func AvgCPUUtilization(c *Container, n *Node) float64 {
	if len(c.CPUCoresHist) == 0 {
		return 0.0
	}
	windowSize := min(len(c.CPUCoresHist), Tmax)
	sum := 0.0
	for i := len(c.CPUCoresHist) - windowSize; i < len(c.CPUCoresHist); i++ {
		if n.CPUCores > 0 {
			sum += c.CPUCoresHist[i] / n.CPUCores
		}
	}
	return sum / float64(windowSize)
}

func AvgMemUtilization(c *Container) float64 {
	if len(c.MemUsedHist) == 0 || c.MemLimit == 0 {
		return 0.0
	}
	windowSize := min(len(c.MemUsedHist), Tmax)
	sum := 0.0
	for i := len(c.MemUsedHist) - windowSize; i < len(c.MemUsedHist); i++ {
		sum += float64(c.MemUsedHist[i]) / float64(c.MemLimit)
	}
	return sum / float64(windowSize)
}

func AvgNodePodMemUtilization(c *Container, n *Node) float64 {
	if len(c.MemUsedHist) == 0 || n.MemSize == 0 {
		return 0.0
	}
	windowSize := min(len(c.MemUsedHist), Tmax)
	sum := 0.0
	for i := len(c.MemUsedHist) - windowSize; i < len(c.MemUsedHist); i++ {
		sum += float64(c.MemUsedHist[i]) / float64(n.MemSize)
	}
	return sum / float64(windowSize)
}

func MemUtilVariance(c *Container) float64 {
	if len(c.MemUsedHist) == 0 || c.MemLimit == 0 {
		return 0.0
	}
	avgUtil := AvgMemUtilization(c)
	windowSize := min(len(c.MemUsedHist), Tmax)
	sumSqDiff := 0.0
	for i := len(c.MemUsedHist) - windowSize; i < len(c.MemUsedHist); i++ {
		util_tk := float64(c.MemUsedHist[i]) / float64(c.MemLimit)
		diff := avgUtil - util_tk
		sumSqDiff += diff * diff
	}
	return sumSqDiff / float64(windowSize)
}

func ResourceMetric(c *Container, n *Node, weights [4]float64) float64 {
	cpuUtil := AvgCPUUtilization(c, n)
	memUtil := AvgMemUtilization(c)
	npmUtil := AvgNodePodMemUtilization(c, n)
	memVar := MemUtilVariance(c)

	return weights[0]*cpuUtil + weights[1]*memUtil + weights[2]*npmUtil + weights[3]*memVar
}

func FEFP(c *Container) float64 {
	if c.Timestamp == 0 {
		return 0.0
	}
	return 1.0 / float64(c.Timestamp)
}

func Penalty(c *Container, n *Node) float64 {
	if n.TotalScaleUps == 0 {
		return 1.0
	}
	return 1.0 - float64(c.ScaleUpCount)/float64(n.TotalScaleUps)
}

func Reward(c *Container) float64 {
	if c.ExecutionTime == 0 {
		return 0.0
	}
	return c.PauseTime / c.ExecutionTime
}

func PriorityScore(c *Container, n *Node, resWeights [4]float64, psWeights [4]float64) float64 {
	R := ResourceMetric(c, n, resWeights)
	fefp := FEFP(c)
	penalty := Penalty(c, n)
	reward := Reward(c)

	return psWeights[0]*R + psWeights[1]*fefp + psWeights[2]*penalty + psWeights[3]*reward
}

func CalculateScaleDown(c *Container) int64 {
	if len(c.MemUsedHist) == 0 {
		return 0
	}
	currentMemUsed := c.MemUsedHist[len(c.MemUsedHist)-1]
	newLimit := float64(currentMemUsed) / MUtilTarget
	scaleDown := c.MemLimit - int64(newLimit)
	if scaleDown < 0 {
		return 0
	}
	return scaleDown
}

func CalculateScaleUp(c *Container) int64 {
	hist := c.MemUsedHist
	windowSize := min(len(hist), Tmax)
	if windowSize < BinSize {
		return 0
	}

	relevantHist := hist[len(hist)-windowSize:]

	numBins := windowSize / BinSize
	if numBins < 2 {
		return 0
	}

	binAvgs := make([]float64, numBins)
	for b := 0; b < numBins; b++ {
		sum := 0.0
		for i := b * BinSize; i < (b+1)*BinSize; i++ {
			sum += float64(relevantHist[i])
		}
		binAvgs[b] = sum / float64(BinSize)
	}

	alpha := 0.8
	scaleUp := 0.0

	for t := 1; t < numBins; t++ {
		g := binAvgs[t] - binAvgs[t-1]
		if g >= 0 {
			f := (float64(Tmax) / float64(BinSize)) * math.Pow(alpha, float64(t)) * g
			scaleUp += f
		}
	}

	return int64(scaleUp)
}

func RunEVMM(
	node *Node,
	Crun []*Container,
	Cpause []*Container,
	Cremove []*Container,
	CisCheckpoint []*Container,
	resWeights [4]float64,
	psWeights [4]float64,
	mu *sync.Mutex,
) {
	allContainers := append(append(Crun, Cpause...), Cremove...)
	for _, c := range allContainers {
		c.PriorityScore = PriorityScore(c, node, resWeights, psWeights)
	}
	sort.Slice(Crun, func(i, j int) bool {
		return Crun[i].PriorityScore > Crun[j].PriorityScore
	})
	sort.Slice(Cpause, func(i, j int) bool {
		return Cpause[i].PriorityScore > Cpause[j].PriorityScore
	})

	allRunAndPause := append(Crun, Cpause...)
	for _, c := range allRunAndPause {
		windowSize := len(c.MemUsedHist)
		memUtil := AvgMemUtilization(c)

		if windowSize > MinTimeWindow && memUtil < ThrScaleDown {
			scaleDownSize := CalculateScaleDown(c)
			if scaleDownSize > 0 {
				ScaleDown(c, scaleDownSize)
			}
		}
	}

	var Cscalecandidate []*Container
	for _, c := range Crun {
		memUtil := AvgMemUtilization(c)

		if memUtil > ThrScaleUp {
			c.ScaleUpSize = CalculateScaleUp(c)
			Cscalecandidate = append(Cscalecandidate, c)
		} else if memUtil <= ThrScaleUp && c.IsPaused {
			ContinueContainer(c)
			c.IsPaused = false
			removePaused(&Cpause, c)
		}
	}

	sort.Slice(Cscalecandidate, func(i, j int) bool {
		return Cscalecandidate[i].PriorityScore > Cscalecandidate[j].PriorityScore
	})

	DecisionScaleUp(node, Cscalecandidate, &Cpause)

	DecisionRemove(node, Crun, &Cpause, &Cremove, &CisCheckpoint)

	for _, c := range Cremove {
		requiredMem := c.MemLimit + c.ScaleUpSize
		if node.MemUsage+requiredMem > node.MemSize {
			break
		}
		RepairContainer(c, c.ScaleUpSize)
		node.MemUsage += requiredMem
		removeFromList(&Cremove, c)
	}
}

func DecisionScaleUp(node *Node, Cscalecandidate []*Container, Cpause *[]*Container) {
	var remaining []*Container

	for _, c := range Cscalecandidate {
		if node.MemUsage+c.ScaleUpSize > node.MemSize {
			remaining = append(remaining, c)
			continue
		}

		node.MemUsage += c.ScaleUpSize
		ScaleUp(c, c.ScaleUpSize)
		c.ScaleUpCount++
		c.MemLimit += c.ScaleUpSize

		if c.IsPaused {
			ContinueContainer(c)
			c.IsPaused = false
			removePaused(Cpause, c)
		}
	}

	for _, c := range remaining {
		PauseContainer(c, QuotaPause)
		c.IsPaused = true
		*Cpause = append(*Cpause, c)
	}
}

func DecisionRemove(
	node *Node,
	Crun []*Container,
	Cpause *[]*Container,
	Cremove *[]*Container,
	CisCheckpoint *[]*Container,
) {
	for _, c := range *Cpause {
		memUtil := AvgMemUtilization(c)
		if memUtil > ThrCheckpoint {
			timeSinceCheckpoint := time.Since(c.LastCheckTime).Seconds()
			if !c.IsCheckpoint || timeSinceCheckpoint > ThrReCheckpoint {
				go CheckpointContainer(c)
				c.IsCheckpoint = true
				c.LastCheckTime = time.Now()
				addOrUpdateCheckpoint(CisCheckpoint, c)
			}
		}
	}

	for _, c := range Crun {
		if isRestarted(c) && c.IsCheckpoint {
			*Cremove = append(*Cremove, c)
		}
	}

	for _, c := range intersection(*CisCheckpoint, *Cpause) {
		nodeMemRatio := float64(node.MemUsage) / float64(node.MemSize)
		if nodeMemRatio > ThrContainerStop {
			go RemoveContainer(c)
			removePaused(Cpause, c)
			*Cremove = append(*Cremove, c)
		}
	}

	for len(*CisCheckpoint) > 0 && countRunning(Crun) < len(*Cpause) {
		candidates := intersection(*CisCheckpoint, *Cpause)
		if len(candidates) == 0 {
			break
		}
		victim := candidates[0]
		go RemoveContainer(victim)
		removePaused(Cpause, victim)
		*Cremove = append(*Cremove, victim)
	}
}

func ScaleUp(c *Container, sizeBytes int64) {
	c.MemLimit += sizeBytes
}

func ScaleDown(c *Container, sizeBytes int64) {
	c.MemLimit -= sizeBytes
}

func PauseContainer(c *Container, cpuQuota int) {
	c.IsPaused = true
}

func ContinueContainer(c *Container) {
	c.IsPaused = false
}

func CheckpointContainer(c *Container) {
	c.IsCheckpoint = true
	c.LastCheckTime = time.Now()
}

func RemoveContainer(c *Container) {
}

func RepairContainer(c *Container, scaleUpSize int64) {
	c.MemLimit += scaleUpSize
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func removePaused(list *[]*Container, target *Container) {
	for i, c := range *list {
		if c.ID == target.ID {
			*list = append((*list)[:i], (*list)[i+1:]...)
			return
		}
	}
}

func removeFromList(list *[]*Container, target *Container) {
	removePaused(list, target)
}

func addOrUpdateCheckpoint(list *[]*Container, target *Container) {
	for _, c := range *list {
		if c.ID == target.ID {
			return
		}
	}
	*list = append(*list, target)
}

func intersection(a, b []*Container) []*Container {
	bMap := make(map[string]bool)
	for _, c := range b {
		bMap[c.ID] = true
	}
	var result []*Container
	for _, c := range a {
		if bMap[c.ID] {
			result = append(result, c)
		}
	}
	return result
}

func countRunning(Crun []*Container) int {
	count := 0
	for _, c := range Crun {
		if !c.IsPaused {
			count++
		}
	}
	return count
}

func isRestarted(c *Container) bool {
	return false
}
