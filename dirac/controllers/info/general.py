import os
import socket

from dirac.lib.base import *
from DIRAC import gConfig, gLogger
from dirac.lib.diset import getRPCClient
from DIRAC.Core.Utilities.List import uniqueElements, fromChar
from dirac.lib.credentials import getUserDN, getUsername, getAvailableGroups
from dirac.lib.credentials import getProperties, checkUserCredentials
from DIRAC.FrameworkSystem.Client.NotificationClient import NotificationClient
from DIRAC.FrameworkSystem.Client.UserProfileClient import UserProfileClient

REG_PROFILE_NAME = "User Registration"

class GeneralController( BaseController ):

  def index( self ):
    return redirect_to( controller = "info/general", action = "diracOverview" )

  def diracOverview( self ):
    return render( "/info/diracOverview.mako" )

  def ext4test( self ):
    return render( "/info/ext4test.mako" )

  @jsonify
  def proxyUpload(self):
    """
    Get p12 file and passwords as input. Split p12 to user key and certificate
    and creating proxy for groups user belongs to. Upload proxy to proxy store
    """
    # Otherwise the browser would offer to download a file
    response.headers['Content-type'] = "text/html"
    username = getUsername()
    gLogger.info("Start upload proxy out of p12 for user: %s" % (username))
    disclaimer  = "\nNo proxy was created\nYour private info was safely deleted"
    disclaimer  = disclaimer + " from DIRAC service"
    if username == "anonymous":
      error = "Please, send a registration request first"
      gLogger.error("Anonymous is not allowed")
      gLogger.debug("Service response: %s" % error)
      return {"success":"false","error":error}
    groupList = getAvailableGroups()
    groups = ", ".join(groupList)
    gLogger.info("Available groups for the user %s: %s" % (username,groups))
    if not len(groupList) > 0:
      gLogger.error("User is not registered in any group")
      error = "Seems that user %s is not register in any group" % username
      error = error + disclaimer
      gLogger.debug("Service response: %s" % error)
      return {"success":"false","error":error}
    store = list()
    gLogger.debug("Request's body:")
    for key in request.params.keys():
      try:
        gLogger.debug("%s - %s" % (key,request.params[key]))
      except Exception,x:
        gLogger.error("Exception: %s" % str(x))
        error  = "An exception has happen '%s'" % str(x)
        error = error + disclaimer
        gLogger.debug("Service response: %s" % error)
        return {"success":"false","error":error}
      try:
        if request.params[key].filename:
          name = request.params[key].filename
          name = name.strip()
          if name[-4:] == ".p12":
            gLogger.info(".p12 in filename detected")
            if request.params["pass_p12"]:
              fileObject = request.params[key]
              fileObject.p12 = str(request.params["pass_p12"])
              gLogger.info(".p12 password detected")
              store.append(fileObject)
              gLogger.info("Certificate object is loaded")
      except Exception,x:
        gLogger.debug("Non fatal for logic, exception happens: %s" % str(x))
        pass
    if not len(store) > 0: # If there is a file(s) to store
      gLogger.error("No file with *.p12 found")
      error = "Failed to find any suitable *.p12 filename in your request"
      error = error + disclaimer
      gLogger.debug("Service response: %s" % error)
      return {"success":"false","error":error}
    gLogger.info("Number of p12 file(s) to process: %s" % len(store))
    import tempfile
    import shutil
    import os
    import random
    import string
    storePath = tempfile.mkdtemp(prefix='DIRAC_')
    gLogger.info("Saving file from request to a tmp directory")
    descriptionList = list()
    try:
      for file in store:
        desc = dict()
        for i in "name","p12","pem":
          tmp = "".join(random.choice(string.letters) for x in range(10))
          desc[i] = os.path.join(storePath,tmp)
        tmpFile = open(desc["name"],"w")
        shutil.copyfileobj(file.file, tmpFile)
        file.file.close()
        tmpFile.close()
        tmpFile = open(desc["p12"],"w")
        tmpFile.write(file.p12)
        tmpFile.close()
        pemPassword = "".join(random.choice(string.letters) for x in range(10))
        tmpFile = open(desc["pem"],"w")
        tmpFile.write(pemPassword)
        tmpFile.close()
        descriptionList.append(desc)
    except Exception,x:
      shutil.rmtree(storePath)
      gLogger.error("Exception: %s" % str(x))
      error  = "An exception has happen '%s'" % str(x)
      error = error + disclaimer
      gLogger.debug("Service response: %s" % error)
      return {"success":"false","error":error}
    if not len(descriptionList) > 0: # If there is a file(s) to store
      shutil.rmtree(storePath)
      gLogger.error("No certificate(s) found")
      error = "List of certificate(s) is empty"
      error = error + disclaimer
      gLogger.debug("Service response: %s" % error)
      return {"success":"false","error":error}
    gLogger.info("Split certificate(s) to public and private keys")
    keyList = list()
    from DIRAC.Core.Utilities import Subprocess
    for i in descriptionList:
      key = dict()
      name = i["name"]
      p12 = i["p12"]
      key["pem"] = i["pem"]
      for j in "pub","private":
        tmp = "".join(random.choice(string.letters) for x in range(10))
        key[j] = os.path.join(storePath,tmp)
      cmdCert = "openssl pkcs12 -clcerts -nokeys -in %s -out %s -password file:%s" % (name,key["pub"],p12)
      cmdKey = "openssl pkcs12 -nocerts -in %s -out %s -passout file:%s -password file:%s" % (name,key["private"],key["pem"],p12)
      for cmd in cmdCert,cmdKey:
        result = Subprocess.shellCall(900,cmd)
        gLogger.debug("Command is: %s" % cmd)
        gLogger.debug("Result is: %s" % result)
        if not result["OK"]:
          shutil.rmtree(storePath)
          gLogger.error(result["Message"])
          error =  "Error while executing SSL command: %s" % result["Message"]
          error = error + disclaimer
          gLogger.debug("Service response: %s" % error)
          return {"success":"false","error":error}
      keyList.append(key)
    if not len(keyList) > 0:
      shutil.rmtree(storePath)
      error = "List of public and private keys is empty"
      gLogger.error(error)
      error = error + disclaimer
      gLogger.debug("Service response: %s" % error)
      return {"success":"false","error":error}
    resultList = list()
    for key in keyList:
      for group in groupList:
        gLogger.info("Uploading proxy for group: %s" % group)
        cmd = "cat %s | dirac-proxy-init -U -g %s -C %s -K %s -p" % (key["pem"],group,key["pub"],key["private"])
        result = Subprocess.shellCall(900,cmd)
        gLogger.debug("Command is: %s" % cmd)
        gLogger.debug("Result is: %s" % result)
        if not result[ 'OK' ]:
          shutil.rmtree(storePath)
          error =  "".join(result["Message"])
          gLogger.error(error)
          if len(resultList) > 0:
            success = "\nHowever some operations has finished successfully:\n"
            success = success + "\n".join(resultList)
            error = error + success
          error = error + disclaimer
          gLogger.debug("Service response: %s" % error)
          return {"success":"false","error":error}
        code = result["Value"][0]
        stdout = result["Value"][1]
        error = result["Value"][2]
        if len(error) > 0:
          error = error.replace(">","")
          error = error.replace("<","")
        if not code == 0:
          if len(resultList) > 0:
            success = "\nHowever some operations has finished successfully:\n"
            success = success + "\n".join(resultList)
            error = error + success
          error = error + disclaimer
          gLogger.debug("Service response: %s" % error)
          return {"success":"false","error":error}
        resultList.append(stdout)
    shutil.rmtree(storePath)
    debug = "\n".join(resultList)
    gLogger.debug(debug)
    groups = ", ".join(groupList)
    result = "Proxy uploaded for user: %s" % username
    if len(groupList) > 0:
      result = result + " in groups: %s" % groups
    else:
      result = result + " in group: %s" % groups
    gLogger.info(result)
    result = "Operation finished successfully\n" + result
    result = result + "\nYour private info was safely deleted from DIRAC server"
    gLogger.debug("Service response: %s" % result)
    return {"success":"true","result":result}
################################################################################
  @jsonify
  def action(self):
    if request.params.has_key("getVOList") and len(request.params["getVOList"]) > 0:
      return {"success":"true","result":self.getVOList()}
    elif request.params.has_key("getCountries") and len(request.params["getCountries"]) > 0:
      return {"success":"true","result":self.getCountries()}
    elif request.params.has_key("registration_request") and len(request.params["registration_request"]) > 0:
      return self.registerUser()
    else:
      return {"success":"false","error":"The request parameters can not be recognized or they are not defined"}
################################################################################



  def alreadyRequested( self , email = False ):

    """
    Checks if the email already saved as registration request key or not
    Return True or False
    """
    
    if not email:
      return True
    upc = UserProfileClient( REG_PROFILE_NAME , getRPCClient )
    result = upc.retrieveVar( email )
    gLogger.info( result )
    if result[ "OK" ]:
      return True
    return False



  def getVOAdmins( self , vo = None ):

    """
    Get admin usernames for VOs in vo list
    Argument is a list. Return value is a list
    """

    names = list()
    if not vo:
      return names
    for i in vo:
      i = i.strip()
      gLogger.debug( "VOAdmin for VO: %s" % i )
      voadmins = gConfig.getValue( "/Registry/VO/%s/VOAdmin" % i , [] )
      gLogger.debug( "/Registry/VO/%s/VOAdmin - %s" % ( i , voadmins ) )
      names.extend( voadmins )

    return names



  def getUserByProperty( self , prop = "NormalUser" ):

    """
    Get usernames based on group property
    Argument is a string. Return value is a list
    """

    groupList = list()
    result = gConfig.getSections( "/Registry/Groups" )
    gLogger.debug( "Group response: %s" % result )
    if not result[ "OK" ]:
      return groupList

    groups = result[ "Value" ]
    for j in groups:
      props = getProperties( j )
      gLogger.debug( "%s properties: %s" % ( j , props ) )
      if prop in props:
        groupList.append( j )

    if not len( groupList ) > 0:
      return groupList
    groupList = uniqueElements( groupList )
    gLogger.debug( "Chosen group(s): %s" % groupList )

    userList = list()
    for i in groupList:
      users = gConfig.getValue( "/Registry/Groups/%s/Users" % i , [] )
      gLogger.debug( "%s users: %s" % ( i , users ) )
      if len( users ) > 0:
        userList.extend( users )

    return userList



  def __getMailDict( self , names = None ):
  
    """
    Convert list of usernames to dict like { e-mail : full name }
    Argument is a list. Return value is a dict
    """

    resultDict = dict()
    if not names:
      return resultDict
    
    for user in names:
      email = gConfig.getValue( "/Registry/Users/%s/Email" % user , "" )
      gLogger.debug( "/Registry/Users/%s/Email - '%s'" % ( user , email ) )
      emil = email.strip()
      
      if not email:
        gLogger.error("Can't find value for option /Registry/Users/%s/Email" % user)
        continue

      fname = gConfig.getValue("/Registry/Users/%s/FullName" % user,"")
      gLogger.debug("/Registry/Users/%s/FullName - '%s'" % (user,fname))
      fname = fname.strip()

      if not fname:
        fname = user
        gLogger.debug("FullName is absent, name to be used: %s" % fname)

      resultDict[email] = fname

    return resultDict



  def __getAdminList( self , vo ):

    """
    Return a list of admins who can register a new user.
    Look first for vo admins then to user with property UserAdministrator and
    looking at /Website/UserRegistrationAdmin as fallback
    """

    adminList = list()
    adminList = self.getVOAdmins( vo )  
    if not len( adminList ) > 0:
      adminList = self.getUserByProperty( "UserAdministrator" )
    if not len( adminList ) > 0:
      adminList = gConfig.getValue( "/Website/UserRegistrationAdmin" , [] )

    if "vhamar" in adminList:
      index = adminList.index( "vhamar" )
      del adminList[ index ]

    return adminList



  def __sendAMail( self , sendDict = None , body = None , sendTo = None ):

    """
    Sending a "new user has registered" email using sendDict: { e-mail : name }
    as source of the info and body as an e-mail body
    Return JSON structure
    """

    if not sendDict:
      result = ""
      gLogger.debug( result )
      return { "success" : "false" , "error" : result }
      
    if not body:
      result = "body argument is missing"
      gLogger.debug( result )
      return { "success" : "false" , "error" : result }

    if not sendTo:
      result = "sendTo argument is missing"
      gLogger.debug( result )
      return { "success" : "false" , "error" : result }

    sentSuccess = list()
    sentFailed = list()
    gLogger.debug( "Initializing Notification client" )
    ntc = NotificationClient( lambda x , timeout: getRPCClient( x , timeout = timeout , static = True ) )

    if socket.gethostname().find( '.' ) >= 0:
      hostname = socket.gethostname()
    else:
      hostname = socket.gethostbyaddr( socket.gethostname() )[ 0 ]
    title = "New user has sent registration request to %s" % hostname

    for email , name in sendDict.iteritems():
      result = ntc.sendMail( email , title , body , sendTo , False )
      if not result[ "OK" ]:
        error = name + ": " + result[ "Message" ]
        sentFailed.append( error )
        gLogger.error( "Sent failure: " , error )
      else:
        gLogger.info( "Successfully sent to %s" % name )
        sentSuccess.append( name )

    success = ", ".join( sentSuccess )
    failure = "\n".join( sentFailed )

    if len( success ) > 0 and len( failure ) > 0:
      result = "Your registration request were sent successfully to: "
      result = result + success + "\n\nFailed to sent it to:\n" + failure
      gLogger.debug( result )
      return { "success" : "true" , "result" : result }
    elif len( success ) > 0 and len( failure ) < 1:
      result = "Your registration request were sent successfully to: %s" % success
      gLogger.debug( result )
      return { "success" : "true" , "result" : result }
    elif len( success ) < 1 and len( failure ) > 0:
      result = "Failed to sent your request to:\n%s" % failure
      gLogger.debug( result )
      return { "success" : "false" , "error" : result }
    else:
      result = "No messages were sent to administrator due technical failure"
      gLogger.debug( result )
      return { "success" : "false" , "error" : result }



  def __checkUnicode( self , name = None , value = None ):

    """
    Check if value is unicode or not and return properly converted string
    Arguments are string and unicode/string, return value is a string
    """

    try:
      value = value.decode( 'utf-8' , "replace" )
    except :
      pass
    value = value.encode( "utf-8" )
    result = "%s - %s" % ( name , value )
    gLogger.debug( result )
    
    return result



  def registerUser( self ):

    """
    This function is used to notify DIRAC admins about user registration request
    The logic is simple:
    0) Check if request from this e-mail has already registered or not
    1) Send mail to VO admin of requested VO
    2) Send mail to users in group with UserAdministrator property
    3) Send mail to users indicated in /Website/UserRegistrationAdmin option
    """
    
    gLogger.info("Start processing a registration request")

    checkUserCredentials()
    # Check for having a DN but no username
    dn = getUserDN()
    if not dn:
      error = "Certificate is not loaded in the browser or DN is absent"
      gLogger.error( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }
    username = getUsername()
    if not username == "anonymous":
      error = "You are already registered in DIRAC with username: %s" % username
      gLogger.error( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }
    gLogger.info( "DN: %s" % dn )

    if not request.params.has_key( "email" ):
      error = "Can not get your email address from the request"
      gLogger.debug( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }
    userMail = request.params[ "email" ]

    if self.alreadyRequested( userMail ):
      error = "Request associated with %s already registered" % userMail
      gLogger.debug( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }

    vo = fromChar( request.params[ "vo" ] )
    if not vo:
      error = "You should indicate a VirtualOrganization for membership"
      gLogger.debug( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }
    gLogger.info( "User want to be register in VO(s): %s" % vo )

    body = str()
    for i in request.params:
      if not i in [ "registration_request" , "email" , "vo" ]:
        info = self.__checkUnicode( i , request.params[ i ] )
        body = body + info + "\n"
    body = body + "DN - " + dn
    gLogger.debug( "email body: %s" % body )

    adminList = self.__getAdminList( vo )
    if not len( adminList ) > 0:
      error = "Can't get in contact with administrators about your request\n"
      error = error + "Most likely this DIRAC instance is not configured yet"
      gLogger.debug( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }
    adminList = uniqueElements( adminList )
    gLogger.info( "Chosen admin(s): %s" % adminList )
    
    sendDict = self.__getMailDict( adminList )
    if not len(sendDict) > 0:
      error = "Can't get in contact with administrators about your request\n"
      error = error + "Most likely this DIRAC instance is not configured yet"
      gLogger.debug( "Service response: %s" % error )
      return { "success" : "false" , "error" : error }
    gLogger.debug( "Final dictionary with mails to be used %s" % sendDict )

    return self.__sendAMail( sendDict , body , userMail )



  def getVOList( self ):

    vo = list()
    result = gConfig.getSections( "/Registry/VO" )
    if result[ "OK" ]:
      vo = result[ "Value" ]

    return vo



  def getCountries( self ):
    countries = {
    "af": "Afghanistan",
    "al": "Albania",
    "dz": "Algeria",
    "as": "American Samoa",
    "ad": "Andorra",
    "ao": "Angola",
    "ai": "Anguilla",
    "aq": "Antarctica",
    "ag": "Antigua and Barbuda",
    "ar": "Argentina",
    "am": "Armenia",
    "aw": "Aruba",
    "au": "Australia",
    "at": "Austria",
    "az": "Azerbaijan",
    "bs": "Bahamas",
    "bh": "Bahrain",
    "bd": "Bangladesh",
    "bb": "Barbados",
    "by": "Belarus",
    "be": "Belgium",
    "bz": "Belize",
    "bj": "Benin",
    "bm": "Bermuda",
    "bt": "Bhutan",
    "bo": "Bolivia",
    "ba": "Bosnia and Herzegowina",
    "bw": "Botswana",
    "bv": "Bouvet Island",
    "br": "Brazil",
    "io": "British Indian Ocean Territory",
    "bn": "Brunei Darussalam",
    "bg": "Bulgaria",
    "bf": "Burkina Faso",
    "bi": "Burundi",
    "kh": "Cambodia",
    "cm": "Cameroon",
    "ca": "Canada",
    "cv": "Cape Verde",
    "ky": "Cayman Islands",
    "cf": "Central African Republic",
    "td": "Chad",
    "cl": "Chile",
    "cn": "China",
    "cx": "Christmas Island",
    "cc": "Cocos Islands",
    "co": "Colombia",
    "km": "Comoros",
    "cg": "Congo",
    "cd": "Congo",
    "ck": "Cook Islands",
    "cr": "Costa Rica",
    "ci": "Cote D'Ivoire",
    "hr": "Croatia",
    "cu": "Cuba",
    "cy": "Cyprus",
    "cz": "Czech Republic",
    "dk": "Denmark",
    "dj": "Djibouti",
    "dm": "Dominica",
    "do": "Dominican Republic",
    "tp": "East Timor",
    "ec": "Ecuador",
    "eg": "Egypt",
    "sv": "El Salvador",
    "gq": "Equatorial Guinea",
    "er": "Eritrea",
    "ee": "Estonia",
    "et": "Ethiopia",
    "fk": "Falkland Islands",
    "fo": "Faroe Islands",
    "fj": "Fiji",
    "fi": "Finland",
    "fr": "France",
    "fx": "France, metropolitan",
    "gf": "French Guiana",
    "pf": "French Polynesia",
    "tf": "French Southern Territories",
    "ga": "Gabon",
    "gm": "Gambia",
    "ge": "Georgia",
    "de": "Germany",
    "gh": "Ghana",
    "gi": "Gibraltar",
    "gr": "Greece",
    "gl": "Greenland",
    "gd": "Grenada",
    "gp": "Guadeloupe",
    "gu": "Guam",
    "gt": "Guatemala",
    "gn": "Guinea",
    "gw": "Guinea-Bissau",
    "gy": "Guyana",
    "ht": "Haiti",
    "hm": "Heard and Mc Donald Islands",
    "va": "Vatican City",
    "hn": "Honduras",
    "hk": "Hong Kong",
    "hu": "Hungary",
    "is": "Iceland",
    "in": "India",
    "id": "Indonesia",
    "ir": "Iran",
    "iq": "Iraq",
    "ie": "Ireland",
    "il": "Israel",
    "it": "Italy",
    "jm": "Jamaica",
    "jp": "Japan",
    "jo": "Jordan",
    "kz": "Kazakhstan",
    "ke": "Kenya",
    "ki": "Kiribati",
    "kp": "Korea",
    "kr": "Korea",
    "kw": "Kuwait",
    "kg": "Kyrgyzstan",
    "la": "Lao",
    "lv": "Latvia",
    "lb": "Lebanon",
    "ls": "Lesotho",
    "lr": "Liberia",
    "ly": "Libyan",
    "li": "Liechtenstein",
    "lt": "Lithuania",
    "lu": "Luxembourg",
    "mo": "Macau",
    "mk": "Macedonia",
    "mg": "Madagascar",
    "mw": "Malawi",
    "my": "Malaysia",
    "mv": "Maldives",
    "ml": "Mali",
    "mt": "Malta",
    "mh": "Marshall Islands",
    "mq": "Martinique",
    "mr": "Mauritania",
    "mu": "Mauritius",
    "yt": "Mayotte",
    "mx": "Mexico",
    "fm": "Micronesia",
    "md": "Moldova",
    "mc": "Monaco",
    "mn": "Mongolia",
    "ms": "Montserrat",
    "ma": "Morocco",
    "mz": "Mozambique",
    "mm": "Myanmar",
    "na": "Namibia",
    "nr": "Nauru",
    "np": "Nepal",
    "nl": "Netherlands",
    "an": "Netherlands Antilles",
    "nc": "New Caledonia",
    "nz": "New Zealand",
    "ni": "Nicaragua",
    "ne": "Niger",
    "ng": "Nigeria",
    "nu": "Niue",
    "nf": "Norfolk Island",
    "mp": "Northern Mariana Islands",
    "no": "Norway",
    "om": "Oman",
    "pk": "Pakistan",
    "pw": "Palau",
    "pa": "Panama",
    "pg": "Papua New Guinea",
    "py": "Paraguay",
    "pe": "Peru",
    "ph": "Philippines",
    "pn": "Pitcairn",
    "pl": "Poland",
    "pt": "Portugal",
    "pr": "Puerto Rico",
    "qa": "Qatar",
    "re": "Reunion",
    "ro": "Romania",
    "ru": "Russia",
    "rw": "Rwanda",
    "kn": "Saint Kitts and Nevis",
    "lc": "Saint Lucia",
    "vc": "Saint Vincent and the Grenadines",
    "ws": "Samoa",
    "sm": "San Marino",
    "st": "Sao Tome and Principe",
    "sa": "Saudi Arabia",
    "sn": "Senegal",
    "sc": "Seychelles",
    "sl": "Sierra Leone",
    "sg": "Singapore",
    "sk": "Slovakia",
    "si": "Slovenia",
    "sb": "Solomon Islands",
    "so": "Somalia",
    "za": "South Africa",
    "gs": "South Georgia and the South Sandwich Islands",
    "es": "Spain",
    "lk": "Sri Lanka",
    "sh": "St. Helena",
    "pm": "St. Pierre and Miquelon",
    "sd": "Sudan",
    "sr": "Suriname",
    "sj": "Svalbard and Jan Mayen Islands",
    "sz": "Swaziland",
    "se": "Sweden",
    "ch": "Switzerland",
    "sy": "Syrian Arab Republic",
    "tw": "Taiwan",
    "tj": "Tajikistan",
    "tz": "Tanzania",
    "th": "Thailand",
    "tg": "Togo",
    "tk": "Tokelau",
    "to": "Tonga",
    "tt": "Trinidad and Tobago",
    "tn": "Tunisia",
    "tr": "Turkey",
    "tm": "Turkmenistan",
    "tc": "Turks and Caicos Islands",
    "tv": "Tuvalu",
    "ug": "Uganda",
    "ua": "Ukraine",
    "ae": "United Arab Emirates",
    "gb": "United Kingdom",
    "uk": "United Kingdom",
    "us": "United States",
    "um": "United States Minor Outlying Islands",
    "uy": "Uruguay",
    "uz": "Uzbekistan",
    "vu": "Vanuatu",
    "ve": "Venezuela",
    "vn": "Viet Nam",
    "vg": "Virgin Islands (British)",
    "vi": "Virgin Islands (U.S.)",
    "wf": "Wallis and Futuna Islands",
    "eh": "Western Sahara",
    "ye": "Yemen",
    "yu": "Yugoslavia",
    "zm": "Zambia",
    "zw": "Zimbabwe",
    "su": "Soviet Union"
    }

    return countries
