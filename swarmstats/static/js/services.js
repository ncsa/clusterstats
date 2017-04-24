function loadData() {
    queue()
        .defer(d3.json, "api/services")
        .await(drawTable);
}

function drawTable(error, services) {
	var rows = [];
	$.each(services, function(k, v) {
		rows.push({
			id: k,
			service: v.name,
			replicas: v.replicas,
			cores: v.cores,
			memory: v.memory,
			disk: v.disk.data,
			action: v.name
		});
	});

	$("#services").bootstrapTable('load', rows);

}

function floatFormatter(x) {
	return d3.format(".2f")(x);
}

function byteFormatter(x) {
	return d3.format(".2s")(x);
}

function serviceRestart(x) {
    console.log("RESTART : " + x);
}

function serviceReload(x) {
    console.log("RELOAD  : " + x);
}

function serviceLogs(x) {
    console.log("LOGS    : " + x);
}

function serviceDestroy(x) {
    console.log("DESTROY : " + x);
}


function actionFormatter(x) {
	return '<a href="services/' + x + '/logs" target="logs">' +
           '<span class="glyphicon glyphicon-list-alt" aria-hidden="true" title="show logs"></span>' +
           // '</a> ' +
           // '<a href="#" onclick="serviceReload(' + x + ')">' +
           // '<span class="glyphicon glyphicon-import" aria-hidden="true" title="download latests"></span>' +
           // '</a> ' +
           // '<a href="#" onclick="serviceRestart(' + x + ')">' +
           // '<span class="glyphicon glyphicon-refresh" aria-hidden="true" title="restart service"></span>' +
           // '</a> ' +
           // '<a href="#" onclick="serviceDestroy(' + x + ')">' +
           // '<span class="glyphicon glyphicon-trash" aria-hidden="true" title="destroy service"></span>' +
           '</a>';
}

$(window).load(loadData);
