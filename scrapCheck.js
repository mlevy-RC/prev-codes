const { google } = require('googleapis');
const AWS = require('aws-sdk');
const fs = require('fs')

AWS.config.update({ region: 'us-west-2' }); 
const dynamoDB = new AWS.DynamoDB.DocumentClient();

/**
 * Query the Portals-dev table and return company names (name attribute).
 */
async function queryCompanyNames() {
    const params = {
        TableName: 'Portals-dev', 
        ProjectionExpression: '#n', // Use a placeholder for the reserved keyword
        ExpressionAttributeNames: {
            '#n': 'name' // Map the placeholder to the actual attribute name
        }
    };

    try {
        // Perform the scan operation
        const data = await dynamoDB.scan(params).promise();
        const companyNames = data.Items.map(item => item.name); // Use the original attribute name when processing the result
        return companyNames;
    } catch (error) {
        console.error('Error querying DynamoDB:', error);
    }
}

/**
 * Compare company names from the spreadsheets and database
 */
async function compareCompanyNames() {
    try {
        const auth = new google.auth.GoogleAuth({
            keyFile: 'credentials.json',
            scopes: ['https://www.googleapis.com/auth/spreadsheets'],
        });

        const sheets = google.sheets({ version: 'v4', auth });

        // Spreadsheet ID and range for the names
        const spreadsheetId1 = '173hddSMo0jw4z1vSmFGool3ZHkoImEWnMBbKpEeOtMY'; 
        const range1 = 'A1:A';  

        // Fetch the names from the Missing Merchants spreadsheet
        const response1 = await sheets.spreadsheets.values.get({
            spreadsheetId: spreadsheetId1,
            range: range1,
        });

        //const names1 = response1.data.values ? response1.data.values.flat() : []; // Ensure data exists

        const data = fs.readFileSync('missing.json', 'utf8');

        // Parse the data into a JavaScript array
        const JBmissing = JSON.parse(data);
        let JBfilter = JBmissing.filter(element => !element.includes("Card Linked"));

        // Fetching the names from the Portal Mapping spreadsheet
        const spreadsheetId = '1AHjv0J9nIjtLBehsypDVOkM4L1Z4PauMv43fJ7QXngc';
        const range = 'Sheet1';
        const response = await sheets.spreadsheets.values.get({
            spreadsheetId,
            range,
        });
        const portalsData = response.data.values;
        //const lastRow = portalsData.length
        const portalsUrlMapping = {};

        for (const [key, value] of portalsData) {
            portalsUrlMapping[key] = value;
        }

        // Runs through the missing merchants and makes it so all of them are lowercase to take away the case sensitive factor 
        // Checks for any company names that include the name of the company (ALDO == Aldo Shoes) 
        JBfilter = JBfilter.map(hold => {
            for (const key in portalsUrlMapping) {
                if (key.toLowerCase().includes(hold.toLowerCase())) {
                    return key;  
                }
            }
            return hold;  // Return the original name if no match is found
        });


        var portalUrl = portalsUrlMapping[JBfilter[0]]

        if (portalUrl){
            console.log("Found", portalUrl)
        }
        else
            console.log("Not Found")
    
        // Fetch the company names from the database
        const companyNames = await queryCompanyNames();

        // Compare the two sets of names
        const matchedNames = JBfilter.filter(name => companyNames.includes(name));

        if (matchedNames.length > 0) {
            console.log('Matched Company Names:', matchedNames.length, matchedNames);
        } else {
            console.log('No matching names found.');
        }

    } catch (error) {
        console.error('Error comparing company names:', error.message);
    }
}

compareCompanyNames()
