var gPlotsList = []; //Valid list of plots
var gTypeName = ""; //Type name
var gMainPanel = false;

function initJobPlots( plotsList, selectionData ){
  gPlotsList = plotsList;
  Ext.onReady(function(){
    renderPage( plotsList, selectionData );
  });
}

function renderPage( plotsList, selectionData ){
  initPlotPage();

  appendToLeftPanel( createComboBox( "plotName", "Plot to generate", "Select a plot", plotsList ) );

  appendTimeSelectorToLeftPanel();

  var selWidgets = []

  if( selectionData.User.length > 1 )
  	selWidgets.push( createMultiselect( "User", "User", selectionData.User ) );
  else
  	selWidgets.push( createHidden( "User", selectionData.User[0] ) );

  if( selectionData.UserGroup.length > 1 )
  	selWidgets.push( createMultiselect( "UserGroup", "User Group", selectionData.UserGroup ) );
  else
  	selWidgets.push( createHidden( "UserGroup", selectionData.UserGroup[0] ) );

  selWidgets.push( createMultiselect( "JobGroup", "Job Group", selectionData.JobGroup ) );
  selWidgets.push( createMultiselect( "JobType", "Job Type", selectionData.JobType ) );
  selWidgets.push( createMultiselect( "JobClass", "Job Class", selectionData.JobClass ) );
  selWidgets.push( createMultiselect( "Site", "Site", selectionData.Site ) );
  selWidgets.push( createMultiselect( "ProcessingType", "Processing Type", selectionData.ProcessingType ) );
  selWidgets.push( createMultiselect( "FinalMajorStatus", "Final major status", selectionData.FinalMajorStatus ) );
  selWidgets.push( createMultiselect( "FinalMinorStatus", "Final minor status", selectionData.FinalMinorStatus ) );
  selWidgets.push( createHidden( "typeName", "Job" ) );
  appendToLeftPanel( createPanel( "Selection conditions", selWidgets ) );

  var orderKeys = []
  for( key in selectionData )
  {
  	orderKeys.push( [ key, key ] );
  }

  appendToLeftPanel( createRadioBoxPanel( "grouping", "Group by", orderKeys ) );

  renderPlotPage();
}