// Time Period
var period = "4hour";
var cluster = "/";
var showmax = getQueryVariable('showmax', 'true') == 'true';

//var cluster = "http://141.142.211.141:9999/";

// Charts
var coresUsageChart = dc.numberDisplay("#cores-usage"),
    coresTotalChart = dc.numberDisplay("#cores-total"),
    coresPercChart = dc.numberDisplay("#cores-perc"),
    memoryUsageChart = dc.numberDisplay("#memory-usage"),
    memoryTotalChart = dc.numberDisplay("#memory-total"),
    memoryPercChart = dc.numberDisplay("#memory-perc"),
    diskUsageChart = dc.numberDisplay("#disk-usage"),
    diskTotalChart = dc.numberDisplay("#disk-total"),
    diskPercChart = dc.numberDisplay("#disk-perc"),
    coresTimeChart = dc.compositeChart('#cores-time'),
    memoryTimeChart = dc.compositeChart('#memory-time'),
    diskTimeChart = dc.compositeChart('#disk-time'),
    serviceCoreschart = dc.rowChart("#service-core"),
    serviceMemorychart = dc.rowChart("#service-memory"),
    // serviceStorageTotalchart = dc.rowChart("#service-disk-total"),
    serviceStorageDatachart = dc.rowChart("#service-disk-data");

var dateToString = function(date) {
    var d = new Date(date);
    if (period == "4hour") {
        return d3.time.format("%X")(d);
    } else {
        return d;
    }
};

function getQueryVariable(variable, defaultval) {
    var query = window.location.search.substring(1);
    var vars = query.split('&');
    for (var i = 0; i < vars.length; i++) {
        var pair = vars[i].split('=');
        if (decodeURIComponent(pair[0]) == variable) {
            return decodeURIComponent(pair[1]);
        }
    }
    return defaultval;
}

function loadData() {
    queue()
        .defer(d3.json, cluster + "swarm/stats/" + period)
        .defer(d3.json, cluster + "services")
        .await(makeGraphs);
}

function makeGraphs(error, swarmStats, services) {

	// Clean the data
	swarmStats.forEach(function(d) {
		d["time"] = Date.parse(d["time"]);
		d["cores"]["total"] = +d["cores"]["total"];
		d["cores"]["used"] = +d["cores"]["used"];
		d["memory"]["total"] = +d["memory"]["total"];
		d["memory"]["used"] = +d["memory"]["used"];
        d["disk"]["available"] = +d["disk"]["available"];
        d["disk"]["used"] = +d["disk"]["used"];
        d["disk"]["data"] = +d["disk"]["data"];
        d["disk"]["image"] = d["disk"]["used"] - d["disk"]["data"];
        d["nodes"] = +d["nodes"];
        d["services"] = +d["services"];
        d["containers"] = +d["containers"];
	});
    services = Object.values(services);

    // Create a Crossfilter instance
    var ndxSwarm = crossfilter(swarmStats),
        ndxServices = crossfilter(services);

    // Define Dimensions
    var swarmDateDim = ndxSwarm.dimension(function(d) { return d["time"]; }),
        servicesNameDim = ndxServices.dimension(function(d) { return d["name"]; });

    // Calculate metrics
	var coreTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["cores"]["total"]; }),
	    coreUsedGroup = swarmDateDim.group().reduceSum(function(d) { return d["cores"]["used"]; }),
	    memoryTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["memory"]["total"]; }),
	    memoryUsedGroup = swarmDateDim.group().reduceSum(function(d) { return d["memory"]["used"]; }),
	    diskTotalGroup = swarmDateDim.group().reduceSum(function(d) { return d["disk"]["available"]; }),
	    diskUsedGroup = swarmDateDim.group().reduceSum(function(d) { return d["disk"]["image"]; }),
	    diskDataGroup = swarmDateDim.group().reduceSum(function(d) { return d["disk"]["data"]; }),
	    servicesCoreGroup = servicesNameDim.group().reduceSum(function(d) { return d["cores"]; }),
	    servicesMemoryGroup = servicesNameDim.group().reduceSum(function(d) { return d["memory"]; }),
	    servicesStorageTotalGroup = servicesNameDim.group().reduceSum(function(d) { return d["disk"]["used"]; }),
	    servicesStorageDataGroup = servicesNameDim.group().reduceSum(function(d) { return d["disk"]["data"]; });

    // Define values (to be used in charts)
    var minDate = swarmDateDim.bottom(1)[0]["time"],
        maxDate = swarmDateDim.top(1)[0]["time"];

	// Create charts
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

    coresTimeChart
		.width(parseInt(d3.select('#cores-time-stage').style('width'), 10))
		.height(240)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
        .dimension(swarmDateDim)
		.transitionDuration(500)
        .keyAccessor(function(d) { return dateToString(d.key); })
        .valueAccessor(function(d) { return d.value; })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .elasticX(true)
        .brushOn(false)
		.yAxis().ticks(4);

    var subcharts = [
        dc.lineChart(coresTimeChart)
            .colors('#1f77b4')
            .group(coreUsedGroup, "Cores Used")
    ];
    if (showmax) {
        subcharts.push(
            dc.lineChart(coresTimeChart)
                .colors('#d62728')
                .group(coreTotalGroup, "Cores Total")
        );
    }
    coresTimeChart.compose(subcharts);

	memoryTimeChart
		.width(parseInt(d3.select('#memory-time-stage').style('width'), 10))
		.height(240)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .yAxisPadding(100)
		.transitionDuration(10)
        .keyAccessor(function(d) { return dateToString(d.key); })
        .valueAccessor(function(d) { return d3.format(".2s")(d.value); })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4)
		.tickFormat(d3.format(".2s"));

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

	diskTimeChart
		.width(parseInt(d3.select('#disk-time-stage').style('width'), 10))
		.height(240)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(swarmDateDim)
        .yAxisPadding(100)
		.transitionDuration(10)
        .keyAccessor(function(d) { return dateToString(d.key); })
        .valueAccessor(function(d) { return d3.format(".2s")(d.value); })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4)
		.tickFormat(d3.format(".2s"));

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

	serviceCoreschart
        .width(parseInt(d3.select('#service-core-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
        .cap(4)
        .othersGrouper(false)
        .group(servicesCoreGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4);

	serviceMemorychart
        .width(parseInt(d3.select('#service-memory-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
        .cap(4)
        .othersGrouper(false)
        .group(servicesMemoryGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4)
        .tickFormat(d3.format(".2s"));

	// serviceStorageTotalchart
     //    .width(parseInt(d3.select('#service-disk-total-stage').style('width'), 10))
     //    .height(130)
     //    .ordering(function(d) { return -d.value; })
     //    .cap(4)
     //    .othersGrouper(false)
     //    .group(servicesStorageTotalGroup)
     //    .dimension(servicesNameDim)
     //    .elasticX(true)
     //    .xAxis().ticks(4)
     //    .tickFormat(d3.format(".2s"));

	serviceStorageDatachart
        .width(parseInt(d3.select('#service-disk-data-stage').style('width'), 10))
        .height(130)
        .ordering(function(d) { return -d.value; })
        .cap(4)
        .othersGrouper(false)
        .group(servicesStorageDataGroup)
        .dimension(servicesNameDim)
        .elasticX(true)
        .xAxis().ticks(4)
        .tickFormat(d3.format(".2s"));

    dc.renderAll();

    setTimeout(loadData, 5 * 60 * 1000);
};

// window.addEventListener('resize', function() {
// 	var width = parseInt(d3.select('#cores-time-stage').style('width'), 10);
// 	coresTimeChart.width(width);
//
// 	dc.renderAll();
// });

window.onload = loadData;
