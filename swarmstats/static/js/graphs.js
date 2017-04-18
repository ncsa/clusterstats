// Time Period
var period = "4hour";

// Charts
var coresTimeChart = dc.compositeChart('#cores-time');
var memoryTimeChart = dc.compositeChart('#memory-time');

var bytesToString = function (bytes) {
    var fmt = d3.format('.0f');
    if (bytes < 1024) {
        return fmt(bytes) + 'B';
    } else if (bytes < 1024 * 1024) {
        return fmt(bytes / 1024) + 'kB';
    } else if (bytes < 1024 * 1024 * 1024) {
        return fmt(bytes / 1024 / 1024) + 'MB';
    } else {
        return fmt(bytes / 1024 / 1024 / 1024) + 'GB';
    }
};

var dateToString = function(date) {
    var d = new Date(date);
    if (period == "4hour") {
        return d3.time.format("%X")(d);
    } else {
        return d;
    }
};

function loadData() {
    queue()
        .defer(d3.json, "/swarm/stats/" + period)
        .await(makeGraphs);
}

function makeGraphs(error, swarmJson) {

	// Clean the data
	var swarmdata = swarmJson;
	swarmdata.forEach(function(d) {
		d["time"] = Date.parse(d["time"]);
		d["cores"]["total"] = +d["cores"]["total"];
		d["cores"]["used"] = +d["cores"]["used"];
		d["memory"]["total"] = +d["memory"]["total"];
		d["memory"]["used"] = +d["memory"]["used"];
	});

    //Create a Crossfilter instance
    var ndx = crossfilter(swarmdata);

    // Define Dimensions
    var dateDim = ndx.dimension(function(d) { return d["time"]; });

    // Calculate metrics
	var coreTotalGroup = dateDim.group().reduceSum(function(d) { return d["cores"]["total"]; });
	var coreUsedGroup = dateDim.group().reduceSum(function(d) { return d["cores"]["used"]; });
	var memoryTotalGroup = dateDim.group().reduceSum(function(d) { return d["memory"]["total"]; });
	var memoryUsedGroup = dateDim.group().reduceSum(function(d) { return d["memory"]["used"]; });

    var all = ndx.groupAll();

    // Define values (to be used in charts)
    var minDate = dateDim.bottom(1)[0]["time"];
    var maxDate = dateDim.top(1)[0]["time"];


    coresTimeChart
		.width(parseInt(d3.select('#cores-time-stage').style('width'), 10))
		.height(240)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
        .dimension(dateDim)
		.compose([
            dc.lineChart(coresTimeChart)
                .colors('black')
                .group(coreTotalGroup, "Cores Total"),
            dc.lineChart(coresTimeChart)
                .colors('#1f77b4')
                .group(coreUsedGroup, "Cores Used")
			])
		.transitionDuration(500)
        .keyAccessor(function(d) { return dateToString(d.key); })
        .valueAccessor(function(d) { return d.value; })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .elasticX(true)
        .brushOn(false)
		.yAxis().ticks(4);

	memoryTimeChart
		.width(parseInt(d3.select('#memory-time-stage').style('width'), 10))
		.height(240)
		.margins({top: 10, right: 50, bottom: 30, left: 50})
		.dimension(dateDim)
        .yAxisPadding(100)
		.compose([
            dc.lineChart(memoryTimeChart)
                .colors('black')
                .group(memoryTotalGroup, "Memory Total"),
            dc.lineChart(memoryTimeChart)
                .colors('#1f77b4')
                .group(memoryUsedGroup, "Memory Used")
			])
		.transitionDuration(10)
        .keyAccessor(function(d) { return dateToString(d.key); })
        .valueAccessor(function(d) { return bytesToString(d.value); })
		.x(d3.time.scale().domain([minDate, maxDate]))
        .yAxisPadding('5%')
		.elasticY(true)
        .brushOn(false)
		.yAxis().ticks(4)
		.tickFormat(bytesToString);

    // resourceTypeChart
    //     .width(300)
    //     .height(250)
    //     .dimension(resourceTypeDim)
    //     .group(numProjectsByResourceType)
    //     .xAxis().ticks(4);
    //
    // povertyLevelChart
		// .width(300)
		// .height(250)
    //     .dimension(povertyLevelDim)
    //     .group(numProjectsByPovertyLevel)
    //     .xAxis().ticks(4);
    //
    //
    // usChart.width(1000)
		// .height(330)
		// .dimension(stateDim)
		// .group(totalDonationsByState)
		// .colors(["#E2F2FF", "#C4E4FF", "#9ED2FF", "#81C5FF", "#6BBAFF", "#51AEFF", "#36A2FF", "#1E96FF", "#0089FF", "#0061B5"])
		// .colorDomain([0, max_state])
		// .overlayGeoJson(statesJson["features"], "state", function (d) {
		// 	return d.properties.name;
		// })
		// .projection(d3.geo.albersUsa()
    // 				.scale(600)
    // 				.translate([340, 150]))
		// .title(function (p) {
		// 	return "State: " + p["key"]
		// 			+ "\n"
		// 			+ "Total Donations: " + Math.round(p["value"]) + " $";
		// })

    dc.renderAll();
};

// window.addEventListener('resize', function() {
// 	var width = parseInt(d3.select('#cores-time-stage').style('width'), 10);
// 	coresTimeChart.width(width);
//
// 	dc.renderAll();
// });

window.onload = loadData;
