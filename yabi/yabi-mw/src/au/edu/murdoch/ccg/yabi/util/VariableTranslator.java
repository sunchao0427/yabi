package au.edu.murdoch.ccg.yabi.util;

import org.jbpm.graph.def.*;
import org.jbpm.graph.exe.*;
import org.jbpm.*;

import java.util.*;

public class VariableTranslator {

    private String separatorRegex = "\\.";
    private String separator = ".";

    //TODO extend so it can be used without an ExecutionContext, but a variable map and a node name
    //retrieves only the variables that fall within the current node's namespace, split into 'input' and 'output' branches of a hashmap
    public Map getVariableMap(ExecutionContext ctx) {
        HashMap relevantVars = new HashMap();
        HashMap inputVars = new HashMap();
        HashMap outputVars = new HashMap();

        //as there is no easy way to get all variables from an ExecutionContext, we use the following convoluted method
        Map vars = ctx.getProcessInstance().getContextInstance().getVariables();
        if (vars != null) {
            Iterator iter = vars.keySet().iterator();
            while (iter.hasNext()) {
                String key = (String) iter.next();
                try {
                    String[] splitName = key.split( separatorRegex );

                    if ( (splitName.length > 2) && (splitName[0].compareTo(getNodeName(ctx)) == 0) ) {
                        //if the variable starts with the current node name then it is one of our variables
                        if ( splitName[1].compareTo("input") == 0 ) {
                            inputVars.put(splitName[2], vars.get(key));
                        }
                        if ( splitName[1].compareTo("output") == 0 ) {
                            outputVars.put(splitName[2], vars.get(key));
                        }
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        }

        //merge vars into a two layer hashmap
        relevantVars.put("input", inputVars);
        relevantVars.put("output", outputVars);

        return relevantVars;
    }

    //reformat context variables for a process instance into a map of node names, each containing a Map of variables
    public Map getVariablesByNode(ProcessInstance pi) {
        Map pivars = pi.getContextInstance().getVariables();
        Map nodes = new HashMap();
        
        Iterator iter = pivars.keySet().iterator();
        while (iter.hasNext()) {
            //each item is a variable. we need to reparse the node, whether it is an input or output variable, and the varname
            String key = (String) iter.next();
            try {
                String[] splitName = key.split( separatorRegex );

                HashMap inputVars = new HashMap();
                HashMap outputVars = new HashMap();

                if (splitName.length > 2) {

                    //fetch node variable map for this node, or create it if it doesn't exist
                    Map nodeVars = (Map) nodes.get(splitName[0]);
                    if (nodeVars == null) {
                        nodeVars = new HashMap();
                        nodeVars.put("input", inputVars);
                        nodeVars.put("output", outputVars);
                        nodes.put(splitName[0], nodeVars);
                    } else { //otherwise set convenience maps for inpu/output vars
                        inputVars = (HashMap) nodeVars.get("input");
                        outputVars = (HashMap) nodeVars.get("output");
                    }

                    if ( splitName[1].compareTo("input") == 0 ) {
                        inputVars.put(splitName[2], pivars.get(key));
                    }
                    if ( splitName[1].compareTo("output") == 0 ) {
                        outputVars.put(splitName[2], pivars.get(key));
                    }
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
 
        }

        return nodes;
        
    }

    //saves the variable 'variableName' as 'nodeName.output.variableName' and searches for substitutions of this
    //variable in the whole namespace
    //this is done by looking for variables that follow the naming schema
    // c.input.filename = derived(b.output.xreffile)
    //will look up the value b.output.xreffile
    //and set c.input.filename to the value of b.output.xreffile 
    public void saveVariable(ExecutionContext ctx, String variableName, Object variableValue) {
        String fullVarName = getNodeName(ctx) + separator + "output" + separator + variableName;

        //first, save the variable as an output variable
        ctx.setVariable( fullVarName, variableValue );

        //define a string that is what the 'derived' string would look like
        String derivedString = "derived("+fullVarName+")";

        List substitutionKeys = new ArrayList();
        //search for substitutions of this variable in the full context variable map
        Iterator iter = ctx.getContextInstance().getVariables().entrySet().iterator();
        while (iter.hasNext()) {
            Map.Entry entry = (Map.Entry) iter.next();

            if ( ((String) entry.getValue()).compareTo( derivedString ) == 0 ) {
                substitutionKeys.add((String)entry.getKey());
            }
        }

        iter = substitutionKeys.iterator();
        while (iter.hasNext()) {
            String key = (String) iter.next();
            ctx.getContextInstance().setVariable( key , variableValue );
        }
    }

    //convenience function for getting the current node name
    protected String getNodeName(ExecutionContext ctx) {
        return ctx.getNode().getFullyQualifiedName();
    }

}
