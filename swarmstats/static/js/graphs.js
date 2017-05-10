// Time Period
var showmax = true;

// Charts
var nodesTotalChart = dc.numberDisplay("#nodes-total"),
    servicesTotalChart = dc.numberDisplay("#services-total"),
    containersTotalChart = dc.numberDisplay("#containers-total"),
    coresUsageChart = dc.numberDisplay("#cores-usage"),
    coresTotalChart = dc.numberDisplay("#cores-total"),
    coresPercChart = dc.numberDisplay("#cores-perc"),
    memoryUsageChart = dc.numberDisplay("#memory-usage"),
    memoryTotalChart = dc.numberDisplay("#memory-total"),
    memoryPercChart = dc.numberDisplay("#memory-perc"),
    diskUsageChart = dc.numberDisplay("#disk-usage"),
    diskTotalChart = dc.numberDisplay("#disk-total"),
    diskPercChart = dc.numberDisplay("#disk-perc"),
    serviceReplicaschart = dc.rowChart("#service-replicas"),
    serviceCoreschart = dc.rowChart("#service-core"),
    serviceMemorychart = dc.rowChart("#service-memory"),
    serviceStorageDatachart = dc.rowChart("#service-disk-data"),
    coresTimeChart = dc.compositeChart('#cores-time'),
    memoryTimeChart = dc.compositeChart('#memory-time'),
    diskTimeChart = dc.compositeChart('#disk-time'),
    nodesTimeChart = dc.lineChart("#nodes-time"),
    servicesTimeChart = dc.lineChart("#services-time"),
    containersTimeChart = dc.lineChart("#containers-time");

var swarmDateDim;
var coresTotalGroup, coresUsedGroup, memoryTotalGroup, memoryUsedGroup,
    diskTotalGroup, diskUsedGroup, diskDataGroup;

function toggleMax() {
    drawSubGraphs();
    coresTimeChart.render();
    memoryTimeChart.render();
    diskTimeChart.render();
}

function loadData() {
    queue()
        .defer(d3.json, "api/swarm/stats/" + $("#period").val())
        .defer(d3.json, "api/services?full=1")
        .await(drawGraphs);
}

function drawGraphs(error, swarmStats, services) {
	// Clean the data
	swarmStats.forEach(function(d) {
		d["time"] = Date.parse(d["time"]);
        d["disk"]["image"] = d["disk"]["used"] - d["disk"]["data"];
	});
    services = Object.values(services);

    // Create a Crossfilter instance
    var ndxSwarm = crossfilter(swarmStats),
        ndxServices = crossfilter(services);

    // swarm
    swarmDateDim = ndxSwarm.dimension(function(d) { return d["time"]; });
	nodesTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["nodes"]; });
	coresTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["cores"]["total"]; });
    coresUsedGroup = swarmDateDim.group().reduceSum(function(d) { return d["cores"]["used"]; });
    memoryTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["memory"]["total"]; });
    memoryUsedGroup = swarmDateDim.group().reduceSum(function(d) { return d["memory"]["used"]; });
    diskTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["disk"]["available"]; });
    diskUsedGroup = swarmDateDim.group().reduceSum(function(d) { return d["disk"]["image"]; });
    diskDataGroup = swarmDateDim.group().reduceSum(function(d) { return d["disk"]["data"]; });
    var servicesTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["services"]; }),
        containersTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["containers"]; });

    // services
    var servicesNameDim = ndxServices.dimension(function(d) { return d["name"]; });
    var servicesCoreGroup = servicesNameDim.group().reduceSum(function(d) { return d["cores"]; }),
        servicesMemoryGroup = servicesNameDim.group().reduceSum(function(d) { return d["memory"]; }),
        servicesReplicasGroup = servicesNameDim.group().reduceSum(function(d) { return d["replicas"]["running"]; }),
        servicesStorageDataGroup = servicesNameDim.group().reduceSum(function(d) { return d["disk"]["data"]; });

    // Define values (to be used in charts)
    var minDate = swarmDateDim.bottom(1)[0]["time"],
        maxDate = swarmDateDim.top(1)[0]["time"];

	// Create charts

    // number charts
	nodesTotalChart
		.formatNumber(d3.format(".0f"))
		.valueAccessor(function(d) { return d.nodes; })
		.group(swarmDateDim);

	servicesTotalChart
		.formatNumber(d3.format(".0f"))
		.valueAccessor(function(d) { return d.services; })
		.group(swarmDateDim);

	containersTotalChart
		.formatNumber(d3.format(".0f"))
		.valueAccessor(function(d) { return d.containers; })
		.group(swarmDateDim);

	coresUsageChart
		.formatNumber(d3.format(".1f"))
		.valueAccessor(function(d) { return d.cores.used; })
		.group(swarmDateDim);

	coresTotalChart
		.formatNumber(d3.format(".0f"))
		.valueAccessor(function(d) { return d.cores.total; })
		.group(swarmDateDim);

	coresPercChart
		.formatNumber(d3.format(".1%"))
		.valueAccessor(function(d) { return d.cores.used / d.cores.total; })
		.group(swarmDateDim);

	memoryUsageChart
		.formatNumber(d3.format(".2s"))
		.valueAccessor(function(d) { return d.memory.used; })
		.group(swarmDateDim);

	memoryTotalChart
		.formatNumber(d3.format(".2s"))
		.valueAccessor(function(d) { return d.memory.total; })
		.group(swarmDateDim);

	memoryPercChart
		.formatNumber(d3.format(".1%"))
		.valueAccessor(function(d) { return d.memory.used / d.memory.total; })
		.group(swarmDateDim);

	diskUsageChart
		.formatNumber(d3.format(".2s"))
		.valueAccessor(function(d) { return d['disk']['used']; })
		.group(swarmDateDim);

	diskTotalChart
		.formatNumber(d3.format(".2s"))
		.valueAccessor(function(d) { return d['disk']['available']; })
		.group(swarmDateDim);

	diskPercChart
		.formatNumber(d3.format(".1%"))
		.valueAccessor(function(d) { return d.disk.used / d.disk.available; })
		.group(swarmDateDim);

    // bar charts
    serviceReplicaschart
        .width(parseInt(d3.select('#service-replicas-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
		.title(function(d) { return d.key + ': ' + d.value; })
        .cap(4)
        .othersGrouper(false)
        .group(servicesReplicasGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4)
        .tickFormat(d3.format("d"));

	serviceCoreschart
        .width(parseInt(d3.select('#service-core-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
		.title(function(d) { return d.key + ': ' + d3.format(".2f")(d.value); })
        .cap(4)
        .othersGrouper(false)
        .group(servicesCoreGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4)
        .tickFormat(d3.format(".2f"));

	serviceMemorychart
        .width(parseInt(d3.select('#service-memory-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
		.title(function(d) { return d.key + ': ' + d3.format(".2s")(d.value); })
        .cap(4)
        .othersGrouper(false)
        .group(servicesMemoryGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4)
        .tickFormat(d3.format(".2s"));

	serviceStorageDatachart
        .width(parseInt(d3.select('#service-disk-data-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
		.title(function(d) { return d.key + ': ' + d3.format(".2s")(d.value); })
        .cap(4)
        .othersGrouper(false)
        .group(servicesStorageDataGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4)
        .tickFormat(d3.format(".2s"));

	// line charts
    coresTimeChart
		.width(parseInt(d3.select('#cores-time-stage').style('width'), 10))
		.height(120)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
        .dimension(swarmDateDim)
		.transitionDuration(500)
        .keyAccessor(function(d) { return d3.time.format("%x %X")(new Date(d.key)); })
        .valueAccessor(function(d) { return d3.format(".2f")(d.value); })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .elasticX(true)
        .brushOn(false)
		.yAxis().ticks(4);

	memoryTimeChart
		.width(parseInt(d3.select('#memory-time-stage').style('width'), 10))
		.height(120)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .yAxisPadding(100)
		.transitionDuration(10)
        .keyAccessor(function(d) { return d3.time.format("%x %X")(new Date(d.key)); })
        .valueAccessor(function(d) { return d3.format(".2s")(d.value); })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4)
		.tickFormat(d3.format(".2s"));

	diskTimeChart
		.width(parseInt(d3.select('#disk-time-stage').style('width'), 10))
		.height(120)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .yAxisPadding(100)
		.transitionDuration(10)
        .keyAccessor(function(d) { return d3.time.format("%x %X")(new Date(d.key)); })
        .valueAccessor(function(d) { return d3.format(".2s")(d.value); })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4)
		.tickFormat(d3.format(".2s"));

	nodesTimeChart
		.width(parseInt(d3.select('#nodes-time-stage').style('width'), 10))
		.height(120)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .group(nodesTotalGroup)
        .yAxisPadding(100)
		.transitionDuration(10)
        .valueAccessor(function(d) { return d.value; })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .title(function(d){ return d3.time.format("%x %X")(new Date(d.key)) + " : " + d3.format(".1f")(d.value); })
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4);

	servicesTimeChart
		.width(parseInt(d3.select('#services-time-stage').style('width'), 10))
		.height(120)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .group(servicesTotalGroup)
        .yAxisPadding(100)
		.transitionDuration(10)
        .valueAccessor(function(d) { return d.value; })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .title(function(d){ return d3.time.format("%x %X")(new Date(d.key)) + " : " + d3.format(".1f")(d.value); })
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4);

	containersTimeChart
		.width(parseInt(d3.select('#containers-time-stage').style('width'), 10))
		.height(120)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .group(containersTotalGroup)
        .yAxisPadding(100)
        .transitionDuration(10)
        .valueAccessor(function(d) { return d.value; })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .title(function(d){ return d3.time.format("%x %X")(new Date(d.key)) + " : " + d3.format(".1f")(d.value); })
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4);

	drawSubGraphs();

    dc.renderAll();

    setTimeout(loadData, 5 * 60 * 1000);
}

function drawSubGraphs() {
    var subcharts = [
        dc.lineChart(coresTimeChart)
            .colors('#1f77b4')
            .group(coresUsedGroup, "Cores Used")
    ];
    if (showmax) {
        subcharts.push(
            dc.lineChart(coresTimeChart)
                .colors('#d62728')
                .group(coresTotalGroup, "Cores Total")
        );
    }
    coresTimeChart.compose(subcharts);

	subcharts = [
        dc.lineChart(memoryTimeChart)
            .colors('#1f77b4')
            .group(memoryUsedGroup, "Memory Used")
    ];
    if (showmax) {
        subcharts.push(
            dc.lineChart(memoryTimeChart)
                .colors('#d62728')
                .group(memoryTotalGroup, "Memory Total")
        );
    }
    memoryTimeChart.compose(subcharts);

    subcharts = [
        dc.lineChart(diskTimeChart)
            .colors('#1f77b4')
            .group(diskUsedGroup, "Disk Used"),
        dc.lineChart(diskTimeChart)
            .colors('#2ca02c')
            .group(diskDataGroup, "Disk Data")
    ];
    if (showmax) {
        subcharts.push(
            dc.lineChart(diskTimeChart)
                .colors('#d62728')
                .group(diskTotalGroup, "Disk Available")
        );
    }
    diskTimeChart.compose(subcharts);

}

$("#period").change(function() {
	localStorage.period = $("#period").val();
	loadData();
});

$("#chkShowMax").click(function() {
    showmax = $('#chkShowMax').is(':checked');
	localStorage.showMaximum = showmax;
	toggleMax();
});

$(window).load(function() {
	if (localStorage.showMaximum) {
		showmax = (localStorage.showMaximum == 'true')
	}
	$('#chkShowMax').prop('checked', showmax);

	if (localStorage.period) {
		$("#period").val(localStorage.period)
    }
	loadData()
});
